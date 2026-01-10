#ifndef SENTRY_PERIPHERALS_RFID_READER_H
#define SENTRY_PERIPHERALS_RFID_READER_H

#include <Arduino.h>
#include "../xConfig.h"

#if RFID_ENABLED
#include <SPI.h>
#include <MFRC522.h>

class RfidReader {
public:
  void begin(uint8_t ssPin, uint8_t rstPin){
    SPI.begin();
    _mfrc = new MFRC522(ssPin, rstPin);
    _mfrc->PCD_Init();
    _lastUid = "";
    _lastSeenMs = 0;
  }

  // Returns true when a new UID is read.
  bool poll(){
    if (!_mfrc) return false;
    if (!_mfrc->PICC_IsNewCardPresent() || !_mfrc->PICC_ReadCardSerial()) return false;

    String uid = uidToHex(_mfrc->uid);
    bool isNew = (uid != _lastUid);

    _lastUid = uid;
    _lastSeenMs = millis();

    _mfrc->PICC_HaltA();
    _mfrc->PCD_StopCrypto1();

    if (isNew){
      _lastEventUid = uid;
      return true;
    }
    return false;
  }

  const String &lastUid() const { return _lastUid; }

  // If a new UID was just read in poll(), returns it once; else empty.
  String takeLastEvent(){
    String t = _lastEventUid;
    _lastEventUid = "";
    return t;
  }

private:
  static String uidToHex(const MFRC522::Uid &u){
    String s;
    for (byte i = 0; i < u.size; i++){
      if (u.uidByte[i] < 16) s += "0";
      s += String(u.uidByte[i], HEX);
    }
    s.toUpperCase();
    return s;
  }

  MFRC522 *_mfrc{nullptr};
  String _lastUid;
  String _lastEventUid;
  unsigned long _lastSeenMs{0};
};
#endif

#endif // SENTRY_PERIPHERALS_RFID_READER_H
