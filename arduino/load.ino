#include <Servo.h>

// ============================================================
// SERVOS
// ============================================================

Servo servoX;
Servo servoY;

const int pinServoX = 9;
const int pinServoY = 11;

// Rangos actuales de Python
const int X_MIN_ANGLE = 0;
const int X_MAX_ANGLE = 70;

const int Y_MIN_ANGLE = 0;
const int Y_MAX_ANGLE = 50;

// ============================================================
// LED
// ============================================================

const int LED_PIN = 13;

// ============================================================
// POSICIÓN
// ============================================================

int currentX = 35;
int currentY = 25;

// ============================================================
// SERIAL
// ============================================================

String inputBuffer = "";

void setup() {
  Serial.begin(115200);

  servoX.attach(pinServoX);
  servoY.attach(pinServoY);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  servoX.write(currentX);
  servoY.write(currentY);

  inputBuffer.reserve(32);
}

void setServos(int x, int y) {
  currentX = constrain(x, X_MIN_ANGLE, X_MAX_ANGLE);
  currentY = constrain(y, Y_MIN_ANGLE, Y_MAX_ANGLE);

  servoX.write(currentX);
  servoY.write(currentY);
}

void processCommand(String command) {
  command.trim();

  if (command.length() == 0) {
    return;
  }

  // ========================================================
  // MANUAL
  // Formato: M,X,Y
  // Ejemplo: M,35,25
  // ========================================================

  if (command.startsWith("M,")) {
    int firstComma = command.indexOf(',');
    int secondComma = command.indexOf(',', firstComma + 1);

    if (secondComma > firstComma) {
      int x = command.substring(
        firstComma + 1,
        secondComma
      ).toInt();

      int y = command.substring(
        secondComma + 1
      ).toInt();

      setServos(x, y);

      // Manual no activa el LED de detección.
      digitalWrite(LED_PIN, LOW);
    }

    return;
  }

  // ========================================================
  // AUTOMÁTICO
  // Formato: X,Y,1
  // ========================================================

  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);

  if (firstComma > 0 && secondComma > firstComma) {

    int x = command.substring(
      0,
      firstComma
    ).toInt();

    int y = command.substring(
      firstComma + 1,
      secondComma
    ).toInt();

    int detected = command.substring(
      secondComma + 1
    ).toInt();

    if (detected == 1) {
      setServos(x, y);
      digitalWrite(LED_PIN, HIGH);
    }

    return;
  }

  // ========================================================
  // OFF
  // Formato: D0
  // ========================================================

  if (command == "D0") {
    digitalWrite(LED_PIN, LOW);
    return;
  }
}

void loop() {

  while (Serial.available() > 0) {

    char c = Serial.read();

    if (c == '\n' || c == '\r') {

      if (inputBuffer.length() > 0) {
        processCommand(inputBuffer);
        inputBuffer = "";
      }

    } else {

      inputBuffer += c;

      // Evita que una comunicación corrupta haga crecer
      // indefinidamente el buffer.
      if (inputBuffer.length() > 40) {
        inputBuffer = "";
      }
    }
  }
}