#include "peripherals/xEbyteRadio.h"
#include "xConfig.h"
#include "peripherals/xLcdDisplay.h"

#include <SPI.h>

EbyteRadio g_ebyteRadio;

EbyteRadio::EbyteRadio(): radio(nullptr), _ce(0), _csn(0), newPacket(false) {}

void EbyteRadio::begin(uint8_t cePin, uint8_t csnPin, uint8_t channel){
  _ce = cePin; _csn = csnPin;
  radio = new RF24(_ce, _csn);
  if (!radio->begin()){
    SERIAL_IO.println(F("EbyteRadio: radio begin failed"));
    return;
  }
  radio->setPALevel(RF24_PA_LOW);
  radio->setChannel(channel);
  radio->setDataRate(RF24_1MBPS);
  radio->enableDynamicPayloads();
  radio->setAutoAck(false);
  radio->openReadingPipe(1, masterAddr);
  radio->openWritingPipe(slaveAddr);
  radio->startListening();
  SERIAL_IO.println(F("EbyteRadio: initialized"));
}

void EbyteRadio::poll(){
  if (!radio) return;
  if (!radio->available()) return;
  uint8_t size = radio->getDynamicPayloadSize();

  // Support two over-the-wire formats for compatibility:
  // 1) Raw MasterPacket1 (5 bytes)
  // 2) Framed: [seq:1][payload:MasterPacket1][crc16:2] => total 8 bytes
  if (size == sizeof(MasterPacket1)){
    radio->read(&lastPkt, size);
    lastSource = "RF_EBYTE";
    newPacket = true;
    sendAck(0, lastPkt, 0);
    String s = String("pkt R(Raw): X=") + lastPkt.Rstick_X + ",Y=" + lastPkt.Rstick_Y + ",B=0x" + String(lastPkt.Buttons, HEX);
    SERIAL_IO.println(s);
  } else if (size == (1 + sizeof(MasterPacket1) + 2)){
    uint8_t buf[1 + sizeof(MasterPacket1) + 2];
    radio->read(buf, sizeof(buf));
    uint8_t seq = buf[0];
    memcpy(&lastPkt, buf + 1, sizeof(MasterPacket1));
    uint16_t rxCrc = (uint16_t)buf[1 + sizeof(MasterPacket1)] | ((uint16_t)buf[1 + sizeof(MasterPacket1) + 1] << 8);
    uint16_t calc = crc16(buf, 1 + sizeof(MasterPacket1));
    if (calc == rxCrc){
      lastSource = String("RF_EBYTE") + "#" + String(seq);
      newPacket = true;
      sendAck(seq, lastPkt, 0);
      String s = String("pkt R(Framed): seq=") + seq + " X=" + lastPkt.Rstick_X + ",Y=" + lastPkt.Rstick_Y + ",B=0x" + String(lastPkt.Buttons, HEX);
      SERIAL_IO.println(s);
    } else {
      sendAck(seq, lastPkt, 1);
      SERIAL_IO.println(F("pkt R: CRC FAIL"));
    }
  } else {
    radio->flush_rx();
  }
}

void EbyteRadio::sendAck(uint8_t seq, const MasterPacket1 &echo, uint8_t status){
  if (!radio) return;
  uint8_t out[1+1+1+1+2];
  out[0] = seq;
  out[1] = (uint8_t)echo.Rstick_X;
  out[2] = (uint8_t)echo.Rstick_Y;
  out[3] = status;
  uint16_t crc = crc16(out, 4);
  out[4] = (uint8_t)(crc & 0xFF);
  out[5] = (uint8_t)((crc >> 8) & 0xFF);

  radio->stopListening();
  bool ok = radio->write(out, sizeof(out));
  if (!ok){ SERIAL_IO.println(F("EbyteRadio: ACK send failed")); }
  radio->startListening();
}

uint16_t EbyteRadio::crc16(const uint8_t *data, size_t len){
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i){
    crc ^= (uint16_t)data[i] << 8;
    for (uint8_t j = 0; j < 8; ++j){
      if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
      else crc <<= 1;
    }
  }
  return crc;
}