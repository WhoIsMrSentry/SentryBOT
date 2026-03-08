#ifndef X_EBYTE_RADIO_H
#define X_EBYTE_RADIO_H

#include <Arduino.h>
#include <RF24.h>

// Minimal EBYTE (nRF24L01 compatible) receiver wrapper for Master packets
// - non-blocking poll() which sets `newPacket` when a fresh packet arrives

struct __attribute__((packed)) MasterPacket1 {
  int8_t  Rstick_X;
  int8_t  Rstick_Y;
  uint8_t R2;
  uint16_t Buttons;
};

class EbyteRadio {
public:
  EbyteRadio();
  void begin(uint8_t cePin, uint8_t csnPin, uint8_t channel = 100);
  void poll(); // call frequently from loop/task

  // Last received packet (valid when newPacket == true until next poll)
  MasterPacket1 lastPkt;
  String lastSource;
  volatile bool newPacket;
  // Send an ACK/telemetry back to the master. Non-blocking-ish (will stop/start listening briefly).
  void sendAck(uint8_t seq, const MasterPacket1 &echo, uint8_t status);

private:
  RF24* radio;
  uint8_t _ce, _csn;
  const uint8_t masterAddr[6] = { 'U','S','T','0','1','\0' }; // ESP master address
  const uint8_t slaveAddr[6]  = { 'A','L','T','0','1','\0' }; // our address
  // CRC helper
  static uint16_t crc16(const uint8_t *data, size_t len);
};

extern EbyteRadio g_ebyteRadio;

#endif // X_EBYTE_RADIO_H
