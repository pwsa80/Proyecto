import cv2
import numpy as np
import time
import serial
import serial.tools.list_ports
import os
from dotenv import load_dotenv

load_dotenv('.env')

# ================= CONFIG =================
USE_IP_CAMERA = True
USE_TRACKBARS = False
USE_SERIAL = True  # 🆕 Activar comunicación serial

if USE_IP_CAMERA:
    CAMERA_SOURCE = os.getenv('VIDEO_LINK')
else:
    CAMERA_SOURCE = 0

TARGET_WIDTH = 1000
TARGET_HEIGHT = 800

# 🎯 Valores de detección
H_BASE = 15
H_MARGIN = 18
S_MIN = 135
V_MIN = 120
S_MAX = 255
V_MAX = 255
MIN_AREA = 500
ASPECT_TOL = 0.6

# 🎯 Parámetros de control de torreta
DEAD_ZONE = 30  # Zona muerta en píxeles (evita microajustes)
SPEED_DIVISOR = 8  # Divide el error para velocidad proporcional

alpha = 0.7
prev_center = None

WIN_NAME = "Tracking Balon Naranja"

# ==========================================

# 🔌 Función para detectar puerto serial automáticamente
def find_arduino_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Detecta Arduino/ESP32 por descripción
        if 'USB' in port.description or 'CH340' in port.description or 'CP210' in port.description:
            return port.device
    return None

# Inicializar serial
ser = None
if USE_SERIAL:
    port = find_arduino_port()
    if port:
        try:
            ser = serial.Serial(port, 115200, timeout=0.01)
            time.sleep(2)  # Esperar a que Arduino reinicie
            print(f"✅ Conectado a {port}")
        except Exception as e:
            print(f"❌ Error al conectar: {e}")
            ser = None
    else:
        print("⚠️ No se detectó Arduino/ESP32")

cap = cv2.VideoCapture(CAMERA_SOURCE)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

cv2.namedWindow(WIN_NAME)

if USE_TRACKBARS:
    cv2.createTrackbar("H", WIN_NAME, H_BASE, 179, lambda x: None)
    cv2.createTrackbar("H_MARGIN", WIN_NAME, H_MARGIN, 50, lambda x: None)
    cv2.createTrackbar("S_MIN", WIN_NAME, S_MIN, 255, lambda x: None)
    cv2.createTrackbar("V_MIN", WIN_NAME, V_MIN, 255, lambda x: None)

prev_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]
    scale = min(TARGET_WIDTH / w, TARGET_HEIGHT / h)
    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

    if USE_TRACKBARS:
        H_BASE = cv2.getTrackbarPos("H", WIN_NAME)
        H_MARGIN = cv2.getTrackbarPos("H_MARGIN", WIN_NAME)
        S_MIN = cv2.getTrackbarPos("S_MIN", WIN_NAME)
        V_MIN = cv2.getTrackbarPos("V_MIN", WIN_NAME)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower = np.array([max(H_BASE - H_MARGIN, 0), S_MIN, V_MIN])
    upper = np.array([min(H_BASE + H_MARGIN, 179), S_MAX, V_MAX])

    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.medianBlur(mask, 5)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_cnt = None
    max_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > MIN_AREA:
            x, y, w_box, h_box = cv2.boundingRect(cnt)
            aspect_ratio = w_box / float(h_box)
            if (1 - ASPECT_TOL) < aspect_ratio < (1 + ASPECT_TOL):
                if area > max_area:
                    best_cnt = cnt
                    max_area = area

    # 🎯 Variables de comando
    command = "S\n"  # Por defecto: Stop
    
    if best_cnt is not None:
        x, y, w_box, h_box = cv2.boundingRect(best_cnt)
        cx = x + w_box // 2
        cy = y + h_box // 2

        if prev_center is None:
            smooth_center = (cx, cy)
        else:
            smooth_center = (
                int(alpha * prev_center[0] + (1 - alpha) * cx),
                int(alpha * prev_center[1] + (1 - alpha) * cy)
            )

        prev_center = smooth_center

        fh, fw = frame.shape[:2]
        frame_center = (fw // 2, fh // 2)

        error_x = smooth_center[0] - frame_center[0]
        error_y = smooth_center[1] - frame_center[1]

        # 🎮 Generar comando solo si está fuera de zona muerta
        if abs(error_x) > DEAD_ZONE or abs(error_y) > DEAD_ZONE:
            # Control proporcional simple
            speed_x = int(np.clip(error_x / SPEED_DIVISOR, -100, 100))
            speed_y = int(np.clip(error_y / SPEED_DIVISOR, -100, 100))
            command = f"M{speed_x:+04d}{speed_y:+04d}\n"
        else:
            command = "S\n"  # Centrado, detener

        # Dibujar
        cv2.rectangle(frame, (x, y), (x + w_box, y + h_box), (0, 165, 255), 3)
        cv2.circle(frame, smooth_center, 5, (255, 255, 255), -1)
        cv2.line(frame, frame_center, smooth_center, (255, 0, 0), 2)

        cv2.putText(frame, f"Error X:{error_x} Y:{error_y}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Cmd: {command.strip()}",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 255), 2)
    else:
        prev_center = None  # Resetear si se pierde el objetivo

    # 📤 Enviar comando por serial
    if ser and ser.is_open:
        try:
            ser.write(command.encode())
        except:
            pass

    # FPS
    curr_time = time.time()
    fps = int(1 / (curr_time - prev_time)) if curr_time != prev_time else 0
    prev_time = curr_time

    cv2.putText(frame, f"FPS: {fps}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow(WIN_NAME, frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Detener torreta antes de cerrar
if ser and ser.is_open:
    ser.write(b"S\n")
    ser.close()

cap.release()
cv2.destroyAllWindows()