from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLD_MINER_DB", str(tmp_path / "players.sqlite3"))
    import app.database as database
    import app.main as main

    importlib.reload(database)
    importlib.reload(main)
    database.init_db()
    return TestClient(main.app)


def test_barcode_credit_pairing_and_rfid_lookup(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/barcode/lookup",
        json={"barcode_id": "934567890123", "player_name": "Michael"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    player = body["player"]
    assert player["credits"] == 0

    response = client.post(
        "/api/credits/add",
        json={"player_id": player["id"], "amount": 50, "source": "test"},
    )
    assert response.status_code == 200
    assert response.json()["player"]["credits"] == 50

    response = client.post(f"/api/players/{player['id']}/pairing-code", json={})
    assert response.status_code == 200
    code = response.json()["code"]
    assert len(code) == 4

    response = client.post("/api/pair-rfid", json={"code": code, "rfid_uid": "04 a1 b2 c3"})
    assert response.status_code == 200
    assert response.json()["player"]["rfid_uid"] == "04A1B2C3"

    response = client.get("/api/rfid/04A1B2C3")
    assert response.status_code == 200
    assert response.json()["player"]["credits"] == 50

    response = client.post(
        "/api/credits/autosave",
        json={"player_id": player["id"], "credits": 65, "source": "slot-1"},
    )
    assert response.status_code == 200
    assert response.json()["player"]["credits"] == 65

    response = client.post(
        "/api/logout-save",
        json={"player_id": player["id"], "credits": 70, "source": "slot-1"},
    )
    assert response.status_code == 200
    assert response.json()["player"]["credits"] == 70

    response = client.get("/api/history?limit=20")
    assert response.status_code == 200
    kinds = [row["kind"] for row in response.json()["history"]]
    assert "account_created" in kinds
    assert "credit_add" in kinds
    assert "rfid_paired" in kinds
    assert "autosave" in kinds
    assert "logout_save" in kinds


def test_negative_balances_are_rejected(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    player = client.post("/api/barcode/lookup", json={"barcode_id": "ABC"}).json()["player"]

    response = client.post(
        "/api/credits/add",
        json={"player_id": player["id"], "amount": -1, "source": "test"},
    )
    assert response.status_code == 400
    assert "below zero" in response.json()["detail"]


def test_pairing_code_cannot_be_reused(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    player = client.post("/api/barcode/lookup", json={"barcode_id": "ABC"}).json()["player"]
    code = client.post(f"/api/players/{player['id']}/pairing-code", json={}).json()["code"]

    assert client.post("/api/pair-rfid", json={"code": code, "rfid_uid": "1111"}).status_code == 200
    response = client.post("/api/pair-rfid", json={"code": code, "rfid_uid": "2222"})
    assert response.status_code == 404
