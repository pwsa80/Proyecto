#include <Servo.h>

Servo servoX;
Servo servoY;

#define SERVO_X_PIN 9
#define SERVO_Y_PIN 11
#define LED_PIN 13

int currentAngleX = 35;
int currentAngleY = 25;

char buffer[32];
byte indexBuffer = 0;

void setup() {

  Serial.begin(115200);

  servoX.attach(SERVO_X_PIN);
  servoY.attach(SERVO_Y_PIN);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  servoX.write(currentAngleX);
  servoY.write(currentAngleY);

  delay(500);
}

void loop() {

  while (Serial.available()) {

    char c = Serial.read();

    if (c == '\n') {

        buffer[indexBuffer] = '\0';

        int angleX;
        int angleY;
        int detected;

        // Comando para apagar el LED
        if (strncmp(buffer, "D0", 2) == 0) {

            digitalWrite(LED_PIN, LOW);

        }

        // Comando de movimiento + detección
        else if (sscanf(buffer, "%d,%d,%d",
                        &angleX,
                        &angleY,
                        &detected) == 3) {

            angleX = constrain(
                angleX,
                0,
                180
            );

            angleY = constrain(
                angleY,
                0,
                180
            );

            if (detected) {

                digitalWrite(LED_PIN, HIGH);

                currentAngleX = angleX;
                currentAngleY = angleY;

                servoX.write(currentAngleX);
                servoY.write(currentAngleY);
            }
        }

        indexBuffer = 0;
    }

    else {

      if (indexBuffer < sizeof(buffer) - 1) {
        buffer[indexBuffer++] = c;
      }
    }
  }
}