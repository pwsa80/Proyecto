######## USAR ESTE CODIGO DE ACUERDO A LA CALIDAD DE VIDEO QUE SE TENGA (BAJA CALIDAD)

import cv2
import numpy as np
import time
import os
from dotenv import load_dotenv
import serial
import serial.tools.list_ports

load_dotenv('.env')

# ================= CONFIG =================

USE_IP_CAMERA = False
USE_TRACKBARS = False
USE_SERIAL = True

if USE_IP_CAMERA:
    CAMERA_SOURCE = os.getenv('VIDEO_LINK')
else:
    CAMERA_SOURCE = 0

TARGET_WIDTH = 1200
TARGET_HEIGHT = 900

# ===== DETECCIÓN =====

H_BASE = 20
H_MARGIN = 20
S_MIN = 140
V_MIN = 120
S_MAX = 255
V_MAX = 255

MIN_AREA = 500
ASPECT_TOL = 0.6

# ===== SUAVIZADO =====

alpha = 0.7
prev_center = None

# ===== SERVO =====

prev_servo = 90
SEND_INTERVAL = 0.015

WIN_NAME = "Tracking Balon Naranja"

# ==========================================

# 🔌 Detección Arduino
def find_arduino_port():

    ports = serial.tools.list_ports.comports()

    print("\n🔍 Buscando Arduino...")

    for port in ports:

        description_lower = port.description.lower()

        arduino_keywords = [
            'arduino',
            'uno',
            'ch340',
            'ch341',
            'usb-serial',
            'usb2.0-serial',
            'atmega328',
            'ftdi',
            'cp210'
        ]

        if any(keyword in description_lower for keyword in arduino_keywords):

            print(f"✅ Arduino detectado: {port.device}")

            return port.device

    print("❌ Arduino no encontrado")

    return None

# ==========================================
# SERIAL
# ==========================================

class SerialCommander:

    def __init__(self, port, baudrate=115200):

        self.ser = serial.Serial(
            port,
            baudrate,
            timeout=0
        )

        time.sleep(2)

        self.last_send_time = 0

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        print(f"✅ Serial conectado: {port}")

    def send(self, angle):

        current_time = time.time()

        if current_time - self.last_send_time < SEND_INTERVAL:
            return

        try:

            self.ser.write(f"{angle}\n".encode())

            self.last_send_time = current_time

        except Exception as e:

            print(f"⚠️ Error serial: {e}")

    def stop(self):

        try:

            self.ser.close()

            print("✅ Serial cerrado")

        except:
            pass

# ==========================================
# INICIALIZAR SERIAL
# ==========================================

serial_cmd = None

if USE_SERIAL:

    port = find_arduino_port()

    if port:

        try:

            serial_cmd = SerialCommander(port)

        except Exception as e:

            print(f"❌ Error serial: {e}")

            serial_cmd = None

# ==========================================
# CÁMARA
# ==========================================

cap = cv2.VideoCapture(CAMERA_SOURCE)

cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():

    print("❌ Error: No se pudo abrir la cámara")

    if serial_cmd:
        serial_cmd.stop()

    exit()

cv2.namedWindow(WIN_NAME)

# ==========================================
# TRACKBARS
# ==========================================

if USE_TRACKBARS:

    cv2.createTrackbar("H", WIN_NAME, H_BASE, 179, lambda x: None)
    cv2.createTrackbar("H_MARGIN", WIN_NAME, H_MARGIN, 50, lambda x: None)
    cv2.createTrackbar("S_MIN", WIN_NAME, S_MIN, 255, lambda x: None)
    cv2.createTrackbar("V_MIN", WIN_NAME, V_MIN, 255, lambda x: None)

# ==========================================

prev_time = time.time()

print("\n🎥 Iniciando tracking...")
print("   Presiona 'q' para salir\n")

# ==========================================
# LOOP
# ==========================================

while True:

    ret, frame = cap.read()

    if not ret:
        break

    # ======================================
    # RESIZE ORIGINAL
    # ======================================

    h, w = frame.shape[:2]

    scale = min(
        TARGET_WIDTH / w,
        TARGET_HEIGHT / h
    )

    frame = cv2.resize(
        frame,
        (int(w * scale), int(h * scale))
    )

    # ======================================
    # TRACKBARS
    # ======================================

    if USE_TRACKBARS:

        H_BASE = cv2.getTrackbarPos("H", WIN_NAME)
        H_MARGIN = cv2.getTrackbarPos("H_MARGIN", WIN_NAME)
        S_MIN = cv2.getTrackbarPos("S_MIN", WIN_NAME)
        V_MIN = cv2.getTrackbarPos("V_MIN", WIN_NAME)

    # ======================================
    # HSV
    # ======================================

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower = np.array([
        max(H_BASE - H_MARGIN, 0),
        S_MIN,
        V_MIN
    ])

    upper = np.array([
        min(H_BASE + H_MARGIN, 179),
        S_MAX,
        V_MAX
    ])

    mask = cv2.inRange(hsv, lower, upper)

    # ======================================
    # LIMPIEZA
    # ======================================

    kernel = np.ones((5, 5), np.uint8)

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        kernel
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    # ======================================
    # CONTORNOS
    # ======================================

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

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

    # ======================================
    # TRACKING
    # ======================================

    if best_cnt is not None:

        x, y, w_box, h_box = cv2.boundingRect(best_cnt)

        cx = x + w_box // 2
        cy = y + h_box // 2

        # ==================================
        # SUAVIZADO
        # ==================================

        if prev_center is None:

            smooth_center = (cx, cy)

        else:

            smooth_center = (
                int(alpha * prev_center[0] + (1 - alpha) * cx),
                int(alpha * prev_center[1] + (1 - alpha) * cy)
            )

        prev_center = smooth_center

        # ==================================
        # ERROR X
        # ==================================

        fh, fw = frame.shape[:2]

        frame_center_x = fw // 2

        error_x = smooth_center[0] - frame_center_x

        # ==================================
        # MAPEO DIRECTO A GRADOS
        # ==================================

        MAX_ERROR = frame_center_x

        servo_angle = np.interp(
            error_x,
            [-MAX_ERROR, MAX_ERROR],
            [0, 180]
        )

        servo_angle = int(
            np.clip(
                servo_angle,
                0,
                180
            )
        )

        # ==================================
        # SUAVIZADO DEL SERVO
        # ==================================

        servo_angle = int(
            prev_servo * 0.7 +
            servo_angle * 0.3
        )

        prev_servo = servo_angle

        # ==================================
        # ENVIAR SERIAL
        # ==================================

        if serial_cmd:

            serial_cmd.send(servo_angle)

        # ==================================
        # VISUAL
        # ==================================

        cv2.rectangle(
            frame,
            (x, y),
            (x + w_box, y + h_box),
            (0, 165, 255),
            3
        )

        cv2.circle(
            frame,
            smooth_center,
            6,
            (255, 255, 255),
            -1
        )

        cv2.line(
            frame,
            (frame_center_x, 0),
            (frame_center_x, fh),
            (255, 0, 0),
            2
        )

        cv2.putText(
            frame,
            f"Error X: {int(error_x)}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        cv2.putText(
            frame,
            f"Servo: {servo_angle}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

    else:

        prev_center = None

    # ======================================
    # FPS
    # ======================================

    curr_time = time.time()

    fps = int(
        1 / (curr_time - prev_time)
    ) if curr_time != prev_time else 0

    prev_time = curr_time

    cv2.putText(
        frame,
        f"FPS: {fps}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    serial_status = (
        "🟢 SERIAL"
        if serial_cmd
        else "🔴 SIN SERIAL"
    )

    cv2.putText(
        frame,
        serial_status,
        (TARGET_WIDTH - 220, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0) if serial_cmd else (0, 0, 255),
        2
    )

    # ======================================
    # SHOW
    # ======================================

    cv2.imshow(WIN_NAME, frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ==========================================
# LIMPIEZA
# ==========================================

print("\n🛑 Cerrando...")

if serial_cmd:
    serial_cmd.stop()

cap.release()

cv2.destroyAllWindows()

print("✅ Finalizado")