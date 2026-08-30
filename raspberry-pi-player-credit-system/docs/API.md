# Slot Game API Notes

The server is meant to run on the Raspberry Pi 3 at a fixed LAN address, for example:

```text
http://192.168.1.50:8000
```

## Normal RFID Login

When the Arduino sends:

```text
RFID:04A1B2C3D4
```

the slot game can look up the account:

```http
GET /api/rfid/04A1B2C3D4
```

Successful response:

```json
{
  "player": {
    "id": 1,
    "barcode_id": "934567890123",
    "rfid_uid": "04A1B2C3D4",
    "player_name": "Player 1",
    "credits": 120,
    "active": true
  }
}
```

If the card is not linked, the server returns `404`.

## Pairing A New RFID Card

The kiosk creates a player from a barcode and displays a 4-digit pairing code.
On the slot machine, enter that code in a dedicated pairing screen, then tap the card.

```http
POST /api/pair-rfid
Content-Type: application/json

{
  "code": "4821",
  "rfid_uid": "04A1B2C3D4"
}
```

The code expires after 5 minutes by default.

## Credit Saves

For local slot gameplay, a practical flow is:

1. Look up the player by RFID.
2. Let the slot game calculate spins, bets, and wins locally.
3. Every 30 seconds, send the current balance to `/api/credits/autosave`.
4. On collect/logout, send the final balance to `/api/logout-save`.

Autosave request:

```http
POST /api/credits/autosave
Content-Type: application/json

{
  "player_id": 1,
  "credits": 135,
  "source": "slot-1",
  "note": "30 second autosave"
}
```

Final logout save:

```http
POST /api/logout-save
Content-Type: application/json

{
  "player_id": 1,
  "credits": 140,
  "source": "slot-1",
  "note": "Player collected and logged out"
}
```

The server rejects negative balances and logs every set/add/save.
