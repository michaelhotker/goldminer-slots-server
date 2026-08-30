from __future__ import annotations

import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import connect, init_db


STATIC_DIR = Path(__file__).resolve().parent / "static"
PAIRING_MINUTES = 5


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Gold Miner Slots Player Credit Server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class BarcodeLookupRequest(BaseModel):
    barcode_id: str = Field(min_length=1, max_length=128)
    player_name: str = Field(default="", max_length=100)


class PairingRequest(BaseModel):
    code: str = Field(min_length=4, max_length=4)
    rfid_uid: str = Field(min_length=1, max_length=64)


class CreditChangeRequest(BaseModel):
    player_id: int
    amount: int
    source: str = Field(default="kiosk", max_length=40)
    note: str = Field(default="", max_length=200)


class CreditSetRequest(BaseModel):
    player_id: int
    credits: int = Field(ge=0)
    source: str = Field(default="slot", max_length=40)
    note: str = Field(default="", max_length=200)


class SessionStartRequest(BaseModel):
    player_id: int
    rfid_uid: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=200)


class SessionEndRequest(BaseModel):
    session_id: int
    final_credits: int = Field(ge=0)
    note: str = Field(default="", max_length=200)


@app.get("/", response_class=HTMLResponse)
def kiosk_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "kiosk.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/barcode/lookup")
def barcode_lookup(payload: BarcodeLookupRequest) -> dict[str, Any]:
    barcode_id = payload.barcode_id.strip()
    if not barcode_id:
        raise HTTPException(status_code=400, detail="barcode_id is required")

    with connect() as conn:
        player = conn.execute("SELECT * FROM players WHERE barcode_id = ?", (barcode_id,)).fetchone()
        created = False
        if player is None:
            conn.execute(
                """
                INSERT INTO players (barcode_id, player_name, credits)
                VALUES (?, ?, 0)
                """,
                (barcode_id, payload.player_name.strip()),
            )
            player = conn.execute("SELECT * FROM players WHERE barcode_id = ?", (barcode_id,)).fetchone()
            created = True
            log_transaction(conn, player["id"], "account_created", 0, 0, 0, "kiosk", "Barcode account created")
        elif payload.player_name.strip() and not player["player_name"]:
            conn.execute(
                "UPDATE players SET player_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (payload.player_name.strip(), player["id"]),
            )
            player = conn.execute("SELECT * FROM players WHERE id = ?", (player["id"],)).fetchone()

        return {"created": created, "player": row_to_player(player)}


@app.get("/api/barcode/{barcode_id}")
def get_by_barcode(barcode_id: str) -> dict[str, Any]:
    with connect() as conn:
        player = conn.execute("SELECT * FROM players WHERE barcode_id = ?", (barcode_id,)).fetchone()
        if player is None:
            raise HTTPException(status_code=404, detail="Barcode account not found")
        return {"player": row_to_player(player)}


@app.get("/api/rfid/{rfid_uid}")
def get_by_rfid(rfid_uid: str, start_session: bool = Query(False)) -> dict[str, Any]:
    uid = normalize_uid(rfid_uid)
    with connect() as conn:
        player = conn.execute("SELECT * FROM players WHERE rfid_uid = ? AND active = 1", (uid,)).fetchone()
        if player is None:
            raise HTTPException(status_code=404, detail="RFID card is not linked")

        result: dict[str, Any] = {"player": row_to_player(player)}
        if start_session:
            cursor = conn.execute(
                """
                INSERT INTO sessions (player_id, rfid_uid, start_credits, note)
                VALUES (?, ?, ?, ?)
                """,
                (player["id"], uid, player["credits"], "Started from RFID lookup"),
            )
            result["session"] = {"id": cursor.lastrowid}
        return result


@app.post("/api/players/{player_id}/pairing-code")
def create_pairing_code(player_id: int) -> dict[str, Any]:
    with connect() as conn:
        player = require_player(conn, player_id)
        expires_at = utc_now() + timedelta(minutes=PAIRING_MINUTES)
        for _ in range(20):
            code = f"{random.randint(0, 9999):04d}"
            try:
                conn.execute(
                    """
                    INSERT INTO pairing_codes (player_id, code, expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (player_id, code, to_db_time(expires_at)),
                )
                return {
                    "code": code,
                    "expires_at": to_db_time(expires_at),
                    "player": row_to_player(player),
                }
            except Exception:
                continue
        raise HTTPException(status_code=500, detail="Could not generate a pairing code")


@app.post("/api/pair-rfid")
def pair_rfid(payload: PairingRequest) -> dict[str, Any]:
    code = payload.code.strip()
    uid = normalize_uid(payload.rfid_uid)
    now = to_db_time(utc_now())

    with connect() as conn:
        existing = conn.execute("SELECT * FROM players WHERE rfid_uid = ?", (uid,)).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="RFID card is already linked to a player")

        pairing = conn.execute(
            """
            SELECT pairing_codes.*, players.credits
            FROM pairing_codes
            JOIN players ON players.id = pairing_codes.player_id
            WHERE code = ? AND used_at IS NULL AND expires_at > ?
            ORDER BY pairing_codes.created_at DESC
            LIMIT 1
            """,
            (code, now),
        ).fetchone()
        if pairing is None:
            raise HTTPException(status_code=404, detail="Pairing code is invalid or expired")

        conn.execute(
            "UPDATE players SET rfid_uid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (uid, pairing["player_id"]),
        )
        conn.execute("UPDATE pairing_codes SET used_at = CURRENT_TIMESTAMP WHERE id = ?", (pairing["id"],))
        player = conn.execute("SELECT * FROM players WHERE id = ?", (pairing["player_id"],)).fetchone()
        log_transaction(conn, player["id"], "rfid_paired", 0, player["credits"], player["credits"], "slot", uid)
        return {"paired": True, "player": row_to_player(player)}


@app.post("/api/credits/add")
def add_credits(payload: CreditChangeRequest) -> dict[str, Any]:
    if payload.amount == 0:
        raise HTTPException(status_code=400, detail="amount must not be zero")
    return change_credits(payload.player_id, payload.amount, "credit_add", payload.source, payload.note)


@app.post("/api/credits/set")
def set_credits(payload: CreditSetRequest) -> dict[str, Any]:
    return set_player_credits(payload.player_id, payload.credits, "credit_set", payload.source, payload.note)


@app.post("/api/credits/autosave")
def autosave(payload: CreditSetRequest) -> dict[str, Any]:
    return set_player_credits(payload.player_id, payload.credits, "autosave", payload.source, payload.note)


@app.post("/api/logout-save")
def logout_save(payload: CreditSetRequest) -> dict[str, Any]:
    return set_player_credits(payload.player_id, payload.credits, "logout_save", payload.source, payload.note)


@app.post("/api/sessions/start")
def start_session(payload: SessionStartRequest) -> dict[str, Any]:
    with connect() as conn:
        player = require_player(conn, payload.player_id)
        cursor = conn.execute(
            """
            INSERT INTO sessions (player_id, rfid_uid, start_credits, note)
            VALUES (?, ?, ?, ?)
            """,
            (payload.player_id, normalize_uid(payload.rfid_uid) if payload.rfid_uid else None, player["credits"], payload.note),
        )
        return {"session": {"id": cursor.lastrowid}, "player": row_to_player(player)}


@app.post("/api/sessions/end")
def end_session(payload: SessionEndRequest) -> dict[str, Any]:
    with connect() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (payload.session_id,)).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        result = set_player_credits_in_conn(
            conn, session["player_id"], payload.final_credits, "logout_save", "slot", payload.note
        )
        conn.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP, end_credits = ?, note = ? WHERE id = ?",
            (payload.final_credits, payload.note, payload.session_id),
        )
        result["session"] = {"id": payload.session_id}
        return result


@app.get("/api/players")
def list_players() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM players ORDER BY updated_at DESC, id DESC").fetchall()
        return {"players": [row_to_player(row) for row in rows]}


@app.get("/api/history")
def history(limit: int = Query(100, ge=1, le=500), player_id: int | None = None) -> dict[str, Any]:
    with connect() as conn:
        if player_id is None:
            rows = conn.execute(
                """
                SELECT transactions.*, players.barcode_id, players.rfid_uid, players.player_name
                FROM transactions
                JOIN players ON players.id = transactions.player_id
                ORDER BY transactions.created_at DESC, transactions.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT transactions.*, players.barcode_id, players.rfid_uid, players.player_name
                FROM transactions
                JOIN players ON players.id = transactions.player_id
                WHERE transactions.player_id = ?
                ORDER BY transactions.created_at DESC, transactions.id DESC
                LIMIT ?
                """,
                (player_id, limit),
            ).fetchall()
        return {"history": [dict(row) for row in rows]}


def change_credits(player_id: int, delta: int, kind: str, source: str, note: str) -> dict[str, Any]:
    with connect() as conn:
        player = require_player(conn, player_id)
        new_credits = player["credits"] + delta
        if new_credits < 0:
            raise HTTPException(status_code=400, detail="Credit balance cannot go below zero")
        return set_player_credits_in_conn(conn, player_id, new_credits, kind, source, note, amount=delta)


def set_player_credits(player_id: int, credits: int, kind: str, source: str, note: str) -> dict[str, Any]:
    with connect() as conn:
        return set_player_credits_in_conn(conn, player_id, credits, kind, source, note)


def set_player_credits_in_conn(
    conn, player_id: int, credits: int, kind: str, source: str, note: str, amount: int | None = None
) -> dict[str, Any]:
    player = require_player(conn, player_id)
    if credits < 0:
        raise HTTPException(status_code=400, detail="Credit balance cannot go below zero")
    delta = credits - player["credits"] if amount is None else amount
    conn.execute(
        "UPDATE players SET credits = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (credits, player_id),
    )
    log_transaction(conn, player_id, kind, delta, player["credits"], credits, source, note)
    updated = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    return {"player": row_to_player(updated)}


def log_transaction(conn, player_id: int, kind: str, amount: int, old_credits: int, new_credits: int, source: str, note: str) -> None:
    conn.execute(
        """
        INSERT INTO transactions (player_id, kind, amount, old_credits, new_credits, source, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (player_id, kind, amount, old_credits, new_credits, source, note),
    )


def require_player(conn, player_id: int):
    player = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


def row_to_player(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "barcode_id": row["barcode_id"],
        "rfid_uid": row["rfid_uid"],
        "player_name": row["player_name"],
        "credits": row["credits"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def normalize_uid(uid: str) -> str:
    return uid.strip().upper().replace(" ", "")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_db_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()
