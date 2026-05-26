#include <Servo.h>

Servo servoX;
Servo servoY;

#define SERVO_X_PIN 9
#define SERVO_Y_PIN 11

int currentAngleX = 90;
int currentAngleY = 90;

char buffer[32];
byte indexBuffer = 0;

void setup() {

  Serial.begin(115200);

  servoX.attach(SERVO_X_PIN);
  servoY.attach(SERVO_Y_PIN);

  servoX.write(currentAngleX);
  servoY.write(currentAngleY);

  delay(500);
}

void loop() {

  while (Serial.available()) {

    char c = Serial.read();

    if (c == '\n') {

      buffer[indexBuffer] = '\0';

      int angleX = 90;
      int angleY = 90;

      sscanf(buffer, "%d,%d", &angleX, &angleY);

      angleX = constrain(angleX, 0, 180);
      angleY = constrain(angleY, 0, 180);

      currentAngleX = angleX;
      currentAngleY = angleY;

      servoX.write(currentAngleX);
      servoY.write(currentAngleY);

      indexBuffer = 0;
    }

    else {

      if (indexBuffer < sizeof(buffer) - 1) {
        buffer[indexBuffer++] = c;
      }
    }
  }
}