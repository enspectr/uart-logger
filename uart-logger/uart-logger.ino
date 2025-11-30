#include <Arduino.h>
#include "hardware/gpio.h"
#include <string.h>

const uint UART0_TX_PIN = 0;
const uint UART0_RX_PIN = 1;
const uint UART1_TX_PIN = 4;
const uint UART1_RX_PIN = 5;

bool sniffing = false;
uint32_t t0 = 0;

char cmdBuf[32];
uint8_t cmdLen = 0;

void setInvert(bool invert) {
  uint mode = invert ? GPIO_OVERRIDE_INVERT : GPIO_OVERRIDE_NORMAL;
  gpio_set_inover(UART0_RX_PIN, mode);
  gpio_set_inover(UART1_RX_PIN, mode);
  gpio_set_outover(UART0_TX_PIN, mode);
  gpio_set_outover(UART1_TX_PIN, mode);
}

void sendRecord(uint8_t chan, uint8_t value) {
  uint8_t rec[6];
  uint32_t t = micros() - t0;
  rec[0] = chan;
  rec[1] = (uint8_t)(t);
  rec[2] = (uint8_t)(t >> 8);
  rec[3] = (uint8_t)(t >> 16);
  rec[4] = (uint8_t)(t >> 24);
  rec[5] = value;
  Serial.write(rec, sizeof(rec));
}

void startSniffer(uint32_t baud, char parity, bool invert) {
  uint32_t config;
  if (parity == 'E' || parity == 'e') {
    config = SERIAL_8E1;
  } else if (parity == 'O' || parity == 'o') {
    config = SERIAL_8O1;
  } else {
    config = SERIAL_8N1;
  }

  Serial1.setTX(UART0_TX_PIN);
  Serial1.setRX(UART0_RX_PIN);
  Serial2.setTX(UART1_TX_PIN);
  Serial2.setRX(UART1_RX_PIN);
  Serial1.begin(baud, config);
  Serial2.begin(baud, config);
  setInvert(invert);
  t0 = micros();
  sniffing = true;
  const char *test0 = "SELFTEST CH0\n";
  const char *test1 = "SELFTEST CH1\n";
  Serial1.write((const uint8_t *)test0, strlen(test0));
  Serial2.write((const uint8_t *)test1, strlen(test1));
}

void handleCommand() {
  if (cmdLen == 0) return;
  if (cmdBuf[0] != 's' && cmdBuf[0] != 'S') return;

  uint32_t baud = 0;
  uint8_t i = 1;

  while (i < cmdLen && cmdBuf[i] >= '0' && cmdBuf[i] <= '9') {
    baud = baud * 10 + (uint32_t)(cmdBuf[i] - '0');
    i++;
  }
  if (baud == 0) return;

  if (i < cmdLen && cmdBuf[i] == ',') i++;

  char parity = 'N';
  if (i < cmdLen) {
    parity = cmdBuf[i];
  }

  while (i < cmdLen && cmdBuf[i] != ',') i++;
  if (i < cmdLen && cmdBuf[i] == ',') i++;

  bool invert = false;
  if (i < cmdLen) {
    char c = cmdBuf[i];
    if (c == 'I' || c == 'i' || c == '1') invert = true;
  }

  startSniffer(baud, parity, invert);
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {
  }
}

void loop() {
  if (!sniffing) {
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\r') continue;
      if (c == '\n') {
        if (cmdLen < sizeof(cmdBuf)) cmdBuf[cmdLen] = '\0';
        handleCommand();
        cmdLen = 0;
      } else {
        if (cmdLen < sizeof(cmdBuf) - 1) {
          cmdBuf[cmdLen++] = c;
        }
      }
    }
    return;
  }

  while (Serial1.available()) {
    sendRecord(0, (uint8_t)Serial1.read());
  }
  while (Serial2.available()) {
    sendRecord(1, (uint8_t)Serial2.read());
  }
}
