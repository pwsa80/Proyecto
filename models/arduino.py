## Actualmente en camera-system
import tkinter as tk
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
MASKON = False
USE_SERIAL = True

if USE_IP_CAMERA:
    CAMERA_SOURCE = os.getenv('VIDEO_LINK')
else:
    CAMERA_SOURCE = 1

TARGET_WIDTH = 1200
TARGET_HEIGHT = 900

# ===== DETECCIÓN RGB =====

# Color objetivo en formato RGB
# Ejemplo: (135, 100, 20)
TARGET_COLOR_RGB = (240, 100, 80)

RGB_MARGIN_R = 30
RGB_MARGIN_G = 30
RGB_MARGIN_B = 30

# Valores máximos y mínimos calculados automáticamente
R_MIN = max(TARGET_COLOR_RGB[0] - RGB_MARGIN_R, 0)
R_MAX = min(TARGET_COLOR_RGB[0] + RGB_MARGIN_R, 255)

G_MIN = max(TARGET_COLOR_RGB[1] - RGB_MARGIN_G, 0)
G_MAX = min(TARGET_COLOR_RGB[1] + RGB_MARGIN_G, 255)

B_MIN = max(TARGET_COLOR_RGB[2] - RGB_MARGIN_B, 0)
B_MAX = min(TARGET_COLOR_RGB[2] + RGB_MARGIN_B, 255)

MIN_AREA = 500
ASPECT_TOL = 0.6

# ===== SUAVIZADO =====

alpha = 0.7
prev_center = None

# ===== SERVOS =====

X_MIN_ANGLE = 0
X_MAX_ANGLE = 70

Y_MIN_ANGLE = 0
Y_MAX_ANGLE = 50

# Centro de los rangos calibrados
CENTER_X = (X_MIN_ANGLE + X_MAX_ANGLE) // 2
CENTER_Y = (Y_MIN_ANGLE + Y_MAX_ANGLE) // 2

prev_servo_x = CENTER_X
prev_servo_y = CENTER_Y

SEND_INTERVAL = 0.015

WIN_NAME = "Tracking"


# ==========================================
# CONFIGURACIÓN RGB
# ==========================================

def create_rgb_window():

    global TARGET_COLOR_RGB
    global RGB_MARGIN_R
    global RGB_MARGIN_G
    global RGB_MARGIN_B

    global R_MIN
    global R_MAX
    global G_MIN
    global G_MAX
    global B_MIN
    global B_MAX

    rgb_window = tk.Tk()

    rgb_window.title("Configuración RGB")
    rgb_window.resizable(False, False)

    # ======================================
    # FUNCIÓN APLICAR
    # ======================================

    def apply_rgb():

        global TARGET_COLOR_RGB
        global RGB_MARGIN_R
        global RGB_MARGIN_G
        global RGB_MARGIN_B

        global R_MIN
        global R_MAX
        global G_MIN
        global G_MAX
        global B_MIN
        global B_MAX

        try:

            r = int(entry_r.get())
            g = int(entry_g.get())
            b = int(entry_b.get())

            margin_r = int(entry_margin_r.get())
            margin_g = int(entry_margin_g.get())
            margin_b = int(entry_margin_b.get())

            # Limitar RGB
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))

            # Limitar márgenes
            margin_r = max(0, min(255, margin_r))
            margin_g = max(0, min(255, margin_g))
            margin_b = max(0, min(255, margin_b))

            # Guardar valores
            TARGET_COLOR_RGB = (r, g, b)

            RGB_MARGIN_R = margin_r
            RGB_MARGIN_G = margin_g
            RGB_MARGIN_B = margin_b

            # Calcular límites
            R_MIN = max(r - margin_r, 0)
            R_MAX = min(r + margin_r, 255)

            G_MIN = max(g - margin_g, 0)
            G_MAX = min(g + margin_g, 255)

            B_MIN = max(b - margin_b, 0)
            B_MAX = min(b + margin_b, 255)

            print("\n🎨 RGB ACTUALIZADO")

            print(
                f"   Objetivo: {TARGET_COLOR_RGB}"
            )

            print(
                f"   R: {R_MIN} - {R_MAX}"
            )

            print(
                f"   G: {G_MIN} - {G_MAX}"
            )

            print(
                f"   B: {B_MIN} - {B_MAX}"
            )

        except ValueError:

            print(
                "⚠️ Introduce solamente números."
            )

    # ======================================
    # TÍTULO
    # ======================================

    tk.Label(
        rgb_window,
        text="COLOR OBJETIVO RGB"
    ).grid(
        row=0,
        column=0,
        columnspan=2,
        pady=8
    )

    # ======================================
    # R
    # ======================================

    tk.Label(
        rgb_window,
        text="R:"
    ).grid(
        row=1,
        column=0,
        padx=10,
        pady=3
    )

    entry_r = tk.Entry(
        rgb_window,
        width=8
    )

    entry_r.insert(
        0,
        str(TARGET_COLOR_RGB[0])
    )

    entry_r.grid(
        row=1,
        column=1,
        padx=10,
        pady=3
    )

    # ======================================
    # G
    # ======================================

    tk.Label(
        rgb_window,
        text="G:"
    ).grid(
        row=2,
        column=0,
        padx=10,
        pady=3
    )

    entry_g = tk.Entry(
        rgb_window,
        width=8
    )

    entry_g.insert(
        0,
        str(TARGET_COLOR_RGB[1])
    )

    entry_g.grid(
        row=2,
        column=1,
        padx=10,
        pady=3
    )

    # ======================================
    # B
    # ======================================

    tk.Label(
        rgb_window,
        text="B:"
    ).grid(
        row=3,
        column=0,
        padx=10,
        pady=3
    )

    entry_b = tk.Entry(
        rgb_window,
        width=8
    )

    entry_b.insert(
        0,
        str(TARGET_COLOR_RGB[2])
    )

    entry_b.grid(
        row=3,
        column=1,
        padx=10,
        pady=3
    )

    # ======================================
    # MÁRGENES
    # ======================================

    tk.Label(
        rgb_window,
        text="MÁRGENES"
    ).grid(
        row=4,
        column=0,
        columnspan=2,
        pady=8
    )

    # Margen R

    tk.Label(
        rgb_window,
        text="Margen R:"
    ).grid(
        row=5,
        column=0,
        padx=10,
        pady=3
    )

    entry_margin_r = tk.Entry(
        rgb_window,
        width=8
    )

    entry_margin_r.insert(
        0,
        str(RGB_MARGIN_R)
    )

    entry_margin_r.grid(
        row=5,
        column=1,
        padx=10,
        pady=3
    )

    # Margen G

    tk.Label(
        rgb_window,
        text="Margen G:"
    ).grid(
        row=6,
        column=0,
        padx=10,
        pady=3
    )

    entry_margin_g = tk.Entry(
        rgb_window,
        width=8
    )

    entry_margin_g.insert(
        0,
        str(RGB_MARGIN_G)
    )

    entry_margin_g.grid(
        row=6,
        column=1,
        padx=10,
        pady=3
    )

    # Margen B

    tk.Label(
        rgb_window,
        text="Margen B:"
    ).grid(
        row=7,
        column=0,
        padx=10,
        pady=3
    )

    entry_margin_b = tk.Entry(
        rgb_window,
        width=8
    )

    entry_margin_b.insert(
        0,
        str(RGB_MARGIN_B)
    )

    entry_margin_b.grid(
        row=7,
        column=1,
        padx=10,
        pady=3
    )

    # ======================================
    # BOTÓN APLICAR
    # ======================================

    tk.Button(
        rgb_window,
        text="APLICAR",
        command=apply_rgb,
        width=15
    ).grid(
        row=8,
        column=0,
        columnspan=2,
        pady=12
    )

    return rgb_window

# ==========================================

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

    def send(self, angle_x, angle_y, detected):

        current_time = time.time()

        if current_time - self.last_send_time < SEND_INTERVAL:
            return

        try:

            if detected:
                command = f"{angle_x},{angle_y},1\n"
            else:
                command = "D0\n"

            self.ser.write(command.encode())

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
# INICIAR CONFIGURACIÓN RGB
# ==========================================

rgb_window = create_rgb_window()


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
    # ACTUALIZAR VENTANA RGB
    # ======================================

    try:

        rgb_window.update_idletasks()
        rgb_window.update()

    except tk.TclError:

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
    # RGB
    # ======================================

    frame_rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    lower = np.array([
        R_MIN,
        G_MIN,
        B_MIN
    ], dtype=np.uint8)

    upper = np.array([
        R_MAX,
        G_MAX,
        B_MAX
    ], dtype=np.uint8)

    mask = cv2.inRange(
        frame_rgb,
        lower,
        upper
    )

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

        fh, fw = frame.shape[:2]

        frame_center_x = fw // 2
        frame_center_y = fh // 2

        # ==================================
        # ERRORES
        # ==================================

        error_x = smooth_center[0] - frame_center_x
        error_y = smooth_center[1] - frame_center_y

        # ==================================
        # MAPEO X
        # ==================================

        MAX_ERROR_X = frame_center_x

        servo_x = np.interp(
            error_x,
            [-MAX_ERROR_X, MAX_ERROR_X],
            [X_MAX_ANGLE, X_MIN_ANGLE]
        )

        servo_x = int(
            np.clip(
                servo_x,
                X_MIN_ANGLE,
                X_MAX_ANGLE
            )
        )

        # ==================================
        # MAPEO Y
        # ==================================

        MAX_ERROR_Y = 400

        servo_y = np.interp(
            error_y,
            [-MAX_ERROR_Y, MAX_ERROR_Y],
            [Y_MIN_ANGLE, Y_MAX_ANGLE]
        )

        servo_y = int(
            np.clip(
                servo_y,
                Y_MIN_ANGLE,
                Y_MAX_ANGLE
            )
        )

        # ==================================
        # SUAVIZADO SERVOS
        # ==================================

        servo_x = int(
            prev_servo_x * 0.7 +
            servo_x * 0.3
        )

        servo_y = int(
            prev_servo_y * 0.7 +
            servo_y * 0.3
        )

        prev_servo_x = servo_x
        prev_servo_y = servo_y

        # ==================================
        # SERIAL
        # ==================================

        if serial_cmd:

            serial_cmd.send(
                servo_x,
                servo_y,
                True
            )

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

        # Línea vertical
        cv2.line(
            frame,
            (frame_center_x, 0),
            (frame_center_x, fh),
            (255, 0, 0),
            2
        )

        # Línea horizontal
        cv2.line(
            frame,
            (0, frame_center_y),
            (fw, frame_center_y),
            (0, 255, 0),
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
            f"Error Y: {int(error_y)}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        cv2.putText(
            frame,
            f"Servo X: {servo_x}",
            (10, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        cv2.putText(
            frame,
            f"Servo Y: {servo_y}",
            (10, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

    else:

        prev_center = None

        if serial_cmd:
            serial_cmd.send(
                0,
                0,
                False
            )

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

    cv2.imshow(WIN_NAME, frame)
    if MASKON:
        cv2.imshow("Mask", mask)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ==========================================

print("\n🛑 Cerrando...")

if serial_cmd:
    serial_cmd.stop()

cap.release()

cv2.destroyAllWindows()

print("✅ Finalizado")