// FocalTech capacitive touch backend - FT6336 (ws_lcd_350, es3n28p, wt32_sc01_plus)
// and FT5X06 (sensecap_indicator, sc05_x). See button_touch_backend.h.
// Both share the same register map: addr 0x38, TD_STATUS at 0x02 (low nibble =
// number of active touch points). BambuHelper only needs the boolean "finger
// down", so the same code drives both - they differ only in which I2C pins the
// bus is brought up on (handled in touchInit below).
#include "button_touch_backend.h"

#if defined(USE_FT5X06) || defined(USE_FT6336)

#include <Wire.h>

#ifndef TOUCH_SLAVE_ADDRESS
#define TOUCH_SLAVE_ADDRESS 0x38
#endif
#define FT5X06_TOUCH_POINTS_REG 0x02  // TD_STATUS register

static bool busReady = false;
static bool seen = false;
static bool edgeDown = false;
static uint8_t consecutiveReadFailures = 0;
static uint32_t totalReadFailures = 0;
static uint32_t busRecoveryCount = 0;
static uint32_t lastGoodPollMs = 0;
static uint32_t lastRecoveryAttemptMs = 0;

#if defined(USE_FT6336)
static void ft6336RecoverBus() {
  // WS350 shares this I2C bus with the TCA9554 LCD-reset expander. Rebind the
  // same pins/clock only; never pulse LCD reset and never reset the FT6336.
  // This repairs a controller path that becomes unreadable after another I2C
  // user or transient bus fault without disturbing the rendered frame.
  const uint32_t now = millis();
  if (lastRecoveryAttemptMs && (uint32_t)(now - lastRecoveryAttemptMs) < 250) return;
  lastRecoveryAttemptMs = now;
  Wire.end();
  delay(2);
  Wire.begin(FT6336_SDA, FT6336_SCL);
  Wire.setClock(400000);
  busReady = true;
  ++busRecoveryCount;
  Serial.printf("FocalTech touch: I2C recovery #%lu on SDA=%d SCL=%d\n",
                (unsigned long)busRecoveryCount, FT6336_SDA, FT6336_SCL);
}
#endif

static bool ft5x06Probe() {
  Wire.beginTransmission(TOUCH_SLAVE_ADDRESS);
  return Wire.endTransmission(true) == 0;
}

static bool ft5x06ReadReg(uint8_t reg, uint8_t& value) {
  Wire.beginTransmission(TOUCH_SLAVE_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)TOUCH_SLAVE_ADDRESS, (uint8_t)1) != 1) return false;
  value = Wire.read();
  return true;
}


// Read first contact coordinates (P1_XH..P1_YL, registers 0x03..0x06).
// FT6336 reports the native portrait sensor space: X=0..319, Y=0..479 on
// ws_lcd_350. Rotation mapping belongs to Smart Home so the backend remains
// reusable by the other FocalTech boards.
static bool ft5x06ReadPoint(uint16_t& x, uint16_t& y) {
  Wire.beginTransmission(TOUCH_SLAVE_ADDRESS);
  Wire.write((uint8_t)0x03);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)TOUCH_SLAVE_ADDRESS, (uint8_t)4) != 4) return false;
  uint8_t xh = Wire.read(), xl = Wire.read(), yh = Wire.read(), yl = Wire.read();
  x = (uint16_t)(((xh & 0x0F) << 8) | xl);
  y = (uint16_t)(((yh & 0x0F) << 8) | yl);
  return true;
}

void touchInit() {
  // Reinitialization must also reset the backend edge state. Recovery can call
  // initButton() at runtime, and retaining a stale held edge would make the UI
  // appear dead even after the bus/controller was successfully reinitialized.
  edgeDown = false;
  consecutiveReadFailures = 0;
  lastGoodPollMs = 0;
#if defined(USE_FT6336)
#if defined(FT6336_RST)
  // Hardware reset before bringing up I2C. The FT6336 RST line is active-LOW; the
  // vendor demo drives HIGH -> LOW -> HIGH with a long settle. Boards that wire
  // RST to a real GPIO (es3n28p, GPIO18) define FT6336_RST; boards that rely on
  // POR (ws_lcd_350) leave it undefined and skip this.
  pinMode(FT6336_RST, OUTPUT);
  digitalWrite(FT6336_RST, HIGH);
  delay(20);
  digitalWrite(FT6336_RST, LOW);
  delay(20);
  digitalWrite(FT6336_RST, HIGH);
  delay(200);  // controller boot after reset release
#endif
  // ws_lcd_350: FT6336 shares the I2C bus that also carries the TCA9554 LCD-reset
  // expander (SDA=8, SCL=7). Reset is handled by the board POR; the retry-at-
  // runtime path covers any startup delay.
  Wire.begin(FT6336_SDA, FT6336_SCL);
#else
  // SenseCAP: FT5X06 shares the PCA9535PW IO-expander I2C bus (SDA=39, SCL=40).
  // Other boards can define FT5X06_SDA/SCL directly.
#if defined(FT5X06_SDA) && defined(FT5X06_SCL)
  Wire.begin(FT5X06_SDA, FT5X06_SCL);
#else
  Wire.begin(39, 40);
#endif
#endif
  Wire.setClock(400000);
  busReady = true;
  delay(50);  // Wait for touch controller to be ready after RST release
  if (ft5x06Probe()) {
    uint8_t touchPoints = 0;
    if (ft5x06ReadReg(FT5X06_TOUCH_POINTS_REG, touchPoints)) {
      Serial.printf("FocalTech touch initialized (I2C addr 0x%02X, touchPoints=%d)\n",
                    TOUCH_SLAVE_ADDRESS, touchPoints);
      seen = true;
    } else {
      Serial.printf("FocalTech touch detected on I2C addr 0x%02X, but register reads failed\n",
                    TOUCH_SLAVE_ADDRESS);
    }
  } else {
    Serial.printf("FocalTech touch did not answer at init (addr 0x%02X); will keep retrying at runtime\n",
                  TOUCH_SLAVE_ADDRESS);
  }
}

TouchPoll touchPoll() {
  if (!busReady) {
#if defined(USE_FT6336)
    ft6336RecoverBus();
#endif
    return {TouchEvent::Unavailable, false};
  }

  uint8_t touchPoints = 0;
  if (!ft5x06ReadReg(FT5X06_TOUCH_POINTS_REG, touchPoints)) {
    ++totalReadFailures;
    if (consecutiveReadFailures < 255) ++consecutiveReadFailures;
#if defined(USE_FT6336)
    // A handful of failed reads is enough to prove the runtime path is unhealthy,
    // but not enough to justify a reboot or a display reset. Rebind I2C in-place.
    if (consecutiveReadFailures >= 3) {
      ft6336RecoverBus();
      consecutiveReadFailures = 0;
    }
#endif
    return {TouchEvent::Unavailable, false};
  }

  consecutiveReadFailures = 0;
  lastGoodPollMs = millis();
  if (!seen) {
    Serial.printf("FocalTech touch became responsive at runtime (addr 0x%02X)\n", TOUCH_SLAVE_ADDRESS);
    seen = true;
  }

  // Capacitive FocalTech panels do not need the generic 50 ms GPIO debounce.
  // Convert the sampled level into explicit edges so even a short tap observed
  // for one loop iteration is accepted immediately. This matters on the richer
  // Smart Home renderer where a frame/service iteration can exceed the old
  // debounce window.
  const bool down = (touchPoints & 0x0F) > 0;
  uint16_t x = 0, y = 0;
  const bool hasPoint = down && ft5x06ReadPoint(x, y);

  if (down && !edgeDown) {
    edgeDown = true;
    return {TouchEvent::Pressed, true, x, y, hasPoint};
  }
  if (!down && edgeDown) {
    edgeDown = false;
    return {TouchEvent::Released, false};
  }
  return {TouchEvent::None, down, x, y, hasPoint};
}

#if defined(USE_FT6336)
uint32_t touchReadFailureCount() { return totalReadFailures; }
uint32_t touchRecoveryCount() { return busRecoveryCount; }
uint32_t touchLastGoodPollMs() { return lastGoodPollMs; }
#endif

#endif  // USE_FT5X06 || USE_FT6336
