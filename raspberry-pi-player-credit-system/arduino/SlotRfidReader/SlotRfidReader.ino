#include <SPI.h>
#include <MFRC522.h>

// Arduino Uno + RC522 wiring:
// RC522 SDA/SS -> D10
// RC522 SCK    -> D13
// RC522 MOSI   -> D11
// RC522 MISO   -> D12
// RC522 RST    -> D9
// RC522 3.3V   -> 3.3V
// RC522 GND    -> GND
//
// Important: power the RC522 from 3.3V, not 5V.

const byte SS_PIN = 10;
const byte RST_PIN = 9;
const unsigned long SAME_CARD_COOLDOWN_MS = 2000;

MFRC522 rfid(SS_PIN, RST_PIN);
String lastUid = "";
unsigned long lastReadAt = 0;

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("READY:RFID");
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  String uid = uidToHex(rfid.uid.uidByte, rfid.uid.size);
  unsigned long now = millis();

  if (uid != lastUid || now - lastReadAt > SAME_CARD_COOLDOWN_MS) {
    Serial.print("RFID:");
    Serial.println(uid);
    lastUid = uid;
    lastReadAt = now;
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

String uidToHex(byte *buffer, byte length) {
  String value = "";
  for (byte i = 0; i < length; i++) {
    if (buffer[i] < 0x10) {
      value += "0";
    }
    value += String(buffer[i], HEX);
  }
  value.toUpperCase();
  return value;
}
