# Gold Miner Slots Player Credit Server

A first working Raspberry Pi 3 friendly player-credit system for a trusted home LAN.

It provides:

- SQLite player database with `barcode_id`, nullable `rfid_uid`, name, credits, active flag, and timestamps
- Transaction/history log for account creation, credit changes, autosaves, logout saves, and card pairing
- Optional session tracking endpoints
- Chromium kiosk page for USB barcode scanners that act like a keyboard and press Enter
- Admin page for players and recent history
- Temporary 4-digit RFID pairing codes that expire after 5 minutes
- Arduino RC522 sketch that prints clean `RFID:<UID>` serial lines

## Project Layout

```text
app/                  FastAPI app and browser screens
arduino/SlotRfidReader RC522 Arduino sketch
docs/API.md           Slot-game API notes
examples/             Small serial-to-API helper example
systemd/              Raspberry Pi service file
data/                 SQLite database location
```

## Run Locally

```bash
cd raspberry-pi-player-credit-system
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- Kiosk: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin`
- API docs: `http://127.0.0.1:8000/docs`

## Raspberry Pi 3 Install

Use Raspberry Pi OS Lite or Desktop. Desktop is easiest if this Pi will also show the kiosk screen.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip chromium-browser unclutter
cd /home/pi
git clone <your repo or copied folder> goldminer-credit-server
cd goldminer-credit-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you copy the folder manually instead of using git, place it at:

```text
/home/pi/goldminer-credit-server
```

Start a test run:

```bash
/home/pi/goldminer-credit-server/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

From another computer on the same network, open:

```text
http://<pi-ip-address>:8000
```

## systemd Service

Copy the service file:

```bash
sudo cp systemd/goldminer-credit-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable goldminer-credit-server
sudo systemctl start goldminer-credit-server
```

Check status:

```bash
systemctl status goldminer-credit-server
```

View logs:

```bash
journalctl -u goldminer-credit-server -f
```

## Chromium Kiosk Autostart

On Raspberry Pi OS Desktop, create:

```bash
mkdir -p /home/pi/.config/lxsession/LXDE-pi
nano /home/pi/.config/lxsession/LXDE-pi/autostart
```

Add:

```text
@xset s off
@xset -dpms
@xset s noblank
@unclutter -idle 0.5
@chromium-browser --kiosk --disable-restore-session-state http://127.0.0.1:8000/
```

Reboot the Pi:

```bash
sudo reboot
```

## Barcode Scanner

Most USB barcode scanners work as keyboards. Configure the scanner to send Enter after each scan. Click the kiosk barcode field once, then scan. The form submits automatically when Enter is received.

## RFID Pairing Flow

1. Scan the player's barcode at the kiosk.
2. Add credits if needed.
3. Press `New RFID Pairing Code`.
4. On the slot machine, choose a dedicated `Link new card` mode and enter that 4-digit code.
5. Tap the RFID card.
6. The slot machine sends the code and card UID to `/api/pair-rfid`.

Normal RFID taps do not pair cards. They only look up an already linked account.

## Arduino RC522 Wiring

Power off before wiring.

| RC522 pin | Arduino Uno pin |
| --- | --- |
| SDA / SS | D10 |
| SCK | D13 |
| MOSI | D11 |
| MISO | D12 |
| RST | D9 |
| 3.3V | 3.3V |
| GND | GND |

Do not connect the RC522 `3.3V` pin to Arduino `5V`.

Install the Arduino library `MFRC522` by Miguel Balboa, then upload:

```text
arduino/SlotRfidReader/SlotRfidReader.ino
```

At 115200 baud, the serial monitor should show:

```text
READY:RFID
RFID:04A1B2C3D4
```

## Trusted LAN Security

This first version intentionally avoids account passwords and complex auth. Use it on a private trusted network only.

Recommended basics:

- Give the Pi a fixed LAN IP address.
- Do not port-forward it to the internet.
- Keep Raspberry Pi OS updated.
- Back up `data/players.sqlite3`.
- If you later use it outside a trusted LAN, add login/auth before exposing it.
