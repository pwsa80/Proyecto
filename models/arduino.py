import cv2
import numpy as np
import time
import os
import tkinter as tk
from tkinter import ttk
from dotenv import load_dotenv
import serial
import serial.tools.list_ports
from PIL import Image, ImageTk

load_dotenv('.env')

# ============================================================
# CONFIGURACIÓN
# ============================================================

USE_IP_CAMERA = False
USE_SERIAL = True
MASKON = False

CAMERA_SOURCE = os.getenv('VIDEO_LINK') if USE_IP_CAMERA else 1

# Resolución interna de procesamiento.
TARGET_WIDTH = 1200
TARGET_HEIGHT = 900

# ============================================================
# DETECCIÓN RGB
# ============================================================

TARGET_COLOR_RGB = [255, 90, 85]

RGB_MARGIN_R = 30
RGB_MARGIN_G = 30
RGB_MARGIN_B = 30

MIN_AREA = 500
ASPECT_TOL = 0.6

# ============================================================
# SUAVIZADO
# ============================================================

alpha = 0.7
prev_center = None

# ============================================================
# SERVOS
# ============================================================

X_MIN_ANGLE = 0
X_MAX_ANGLE = 70

Y_MIN_ANGLE = 0
Y_MAX_ANGLE = 50

CENTER_X = (X_MIN_ANGLE + X_MAX_ANGLE) / 2
CENTER_Y = (Y_MIN_ANGLE + Y_MAX_ANGLE) / 2

current_servo_x = float(CENTER_X)
current_servo_y = float(CENTER_Y)

MANUAL_SPEED_X = 45.0
MANUAL_SPEED_Y = 35.0

CLICK_SPEED_X = 80.0
CLICK_SPEED_Y = 60.0

SEND_INTERVAL = 0.015

# ============================================================
# SERIAL
# ============================================================

def find_arduino_port():
    ports = serial.tools.list_ports.comports()

    print("\n🔍 Buscando Arduino...")

    for port in ports:
        description_lower = port.description.lower()

        keywords = [
            'arduino', 'uno', 'ch340', 'ch341',
            'usb-serial', 'usb2.0-serial',
            'atmega328', 'ftdi', 'cp210'
        ]

        if any(keyword in description_lower for keyword in keywords):
            print(f"✅ Arduino detectado: {port.device}")
            return port.device

    print("❌ Arduino no encontrado")
    return None


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

    def _send_raw(self, command):
        current_time = time.time()

        if current_time - self.last_send_time < SEND_INTERVAL:
            return

        try:
            self.ser.write(command.encode())
            self.last_send_time = current_time
        except Exception as e:
            print(f"⚠️ Error serial: {e}")

    def send_auto(self, angle_x, angle_y):
        self._send_raw(f"{int(angle_x)},{int(angle_y)},1\n")

    def send_manual(self, angle_x, angle_y):
        self._send_raw(f"M,{int(angle_x)},{int(angle_y)}\n")

    def send_off(self):
        self._send_raw("D0\n")

    def stop(self):
        try:
            self.ser.close()
        except Exception:
            pass


serial_cmd = None

if USE_SERIAL:
    port = find_arduino_port()

    if port:
        try:
            serial_cmd = SerialCommander(port)
        except Exception as e:
            print(f"❌ Error serial: {e}")

# ============================================================
# CÁMARA
# ============================================================

cap = cv2.VideoCapture(CAMERA_SOURCE)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print("❌ No se pudo abrir la cámara")

    if serial_cmd:
        serial_cmd.stop()

    raise SystemExit

# ============================================================
# ESTADO
# ============================================================

mode = "AUTO"

joystick_x = 0.0
joystick_y = 0.0
joystick_active = False

click_target_x = None
click_target_y = None

# Cuentagotas
eyedropper_active = False

# Frame actual EXACTAMENTE igual al mostrado.
current_frame_for_picker = None
display_width = 0
display_height = 0

photo_image = None

# ============================================================
# RGB
# ============================================================

def build_rgb_mask(frame):
    r_target, g_target, b_target = TARGET_COLOR_RGB

    lower_r = max(0, r_target - RGB_MARGIN_R)
    upper_r = min(255, r_target + RGB_MARGIN_R)

    lower_g = max(0, g_target - RGB_MARGIN_G)
    upper_g = min(255, g_target + RGB_MARGIN_G)

    lower_b = max(0, b_target - RGB_MARGIN_B)
    upper_b = min(255, b_target + RGB_MARGIN_B)

    b, g, r = cv2.split(frame)

    mask_r = cv2.inRange(r, lower_r, upper_r)
    mask_g = cv2.inRange(g, lower_g, upper_g)
    mask_b = cv2.inRange(b, lower_b, upper_b)

    mask = cv2.bitwise_and(mask_r, mask_g)
    mask = cv2.bitwise_and(mask, mask_b)

    return mask


# ============================================================
# MAPEO
# ============================================================

def pixel_to_servo_x(pixel_x, width):
    return float(np.interp(
        pixel_x,
        [0, width - 1],
        [X_MAX_ANGLE, X_MIN_ANGLE]
    ))


def pixel_to_servo_y(pixel_y, height):
    return float(np.interp(
        pixel_y,
        [0, height - 1],
        [Y_MIN_ANGLE, Y_MAX_ANGLE]
    ))


def servo_to_pixel_x(angle_x, width):
    return int(np.interp(
        angle_x,
        [X_MIN_ANGLE, X_MAX_ANGLE],
        [width - 1, 0]
    ))


def servo_to_pixel_y(angle_y, height):
    return int(np.interp(
        angle_y,
        [Y_MIN_ANGLE, Y_MAX_ANGLE],
        [0, height - 1]
    ))


def clamp_servo_angles():
    global current_servo_x, current_servo_y

    current_servo_x = float(np.clip(
        current_servo_x,
        X_MIN_ANGLE,
        X_MAX_ANGLE
    ))

    current_servo_y = float(np.clip(
        current_servo_y,
        Y_MIN_ANGLE,
        Y_MAX_ANGLE
    ))


def move_towards(current, target, max_delta):
    difference = target - current

    if abs(difference) <= max_delta:
        return target

    return current + np.sign(difference) * max_delta


# ============================================================
# JOYSTICK
# ============================================================

JOYSTICK_SIZE = 220
JOYSTICK_CENTER = JOYSTICK_SIZE // 2
JOYSTICK_RADIUS = 80
KNOB_RADIUS = 25

joystick_canvas = None
joystick_knob = None


def update_joystick_visual():
    if joystick_canvas is None or joystick_knob is None:
        return

    knob_x = JOYSTICK_CENTER + joystick_x * JOYSTICK_RADIUS
    knob_y = JOYSTICK_CENTER + joystick_y * JOYSTICK_RADIUS

    joystick_canvas.coords(
        joystick_knob,
        knob_x - KNOB_RADIUS,
        knob_y - KNOB_RADIUS,
        knob_x + KNOB_RADIUS,
        knob_y + KNOB_RADIUS
    )


def set_joystick_from_event(event):
    global joystick_x, joystick_y

    if mode != "MANUAL":
        return

    dx = event.x - JOYSTICK_CENTER
    dy = event.y - JOYSTICK_CENTER

    distance = np.sqrt(dx * dx + dy * dy)

    if distance > JOYSTICK_RADIUS:
        factor = JOYSTICK_RADIUS / distance
        dx *= factor
        dy *= factor

    joystick_x = float(np.clip(dx / JOYSTICK_RADIUS, -1, 1))
    joystick_y = float(np.clip(dy / JOYSTICK_RADIUS, -1, 1))

    update_joystick_visual()


def joystick_press(event):
    global joystick_active

    if mode != "MANUAL":
        return

    joystick_active = True
    set_joystick_from_event(event)


def joystick_drag(event):
    if mode != "MANUAL" or not joystick_active:
        return

    set_joystick_from_event(event)


def joystick_release(event):
    global joystick_active, joystick_x, joystick_y

    joystick_active = False
    joystick_x = 0.0
    joystick_y = 0.0

    update_joystick_visual()


def reset_joystick():
    global joystick_x, joystick_y, joystick_active

    joystick_x = 0.0
    joystick_y = 0.0
    joystick_active = False

    update_joystick_visual()


# ============================================================
# CUENTAGOTAS
# ============================================================

def toggle_eyedropper():
    global eyedropper_active

    eyedropper_active = not eyedropper_active

    if eyedropper_active:
        eyedropper_button.configure(text="CANCELAR CUENTAGOTAS")
        eyedropper_status_var.set(
            "🖊️ Cuentagotas activo: haz click sobre la cámara"
        )
        camera_label.configure(cursor="crosshair")
    else:
        eyedropper_button.configure(text="CUENTAGOTAS")
        eyedropper_status_var.set("")
        camera_label.configure(cursor="")


def pick_rgb_from_display(event):
    global TARGET_COLOR_RGB, eyedropper_active

    if not eyedropper_active:
        return False

    if current_frame_for_picker is None:
        return True

    h, w = current_frame_for_picker.shape[:2]

    if display_width <= 0 or display_height <= 0:
        return True

    # Como la imagen mostrada y la imagen usada por el picker
    # tienen exactamente display_width x display_height,
    # no hay offset de un cuadro externo que pueda desplazar el click.
    x = int(event.x * w / display_width)

    # Corrección del desfase vertical de 4°
    y = int(event.y * h / display_height)

    y += int((4 / (Y_MAX_ANGLE - Y_MIN_ANGLE)) * (h - 1))

    x = int(np.clip(x, 0, w - 1))
    y = int(np.clip(y, 0, h - 1))

    # frame interno es BGR
    b, g, r = current_frame_for_picker[y, x]

    TARGET_COLOR_RGB = [int(r), int(g), int(b)]

    rgb_r_entry.delete(0, tk.END)
    rgb_r_entry.insert(0, str(int(r)))

    rgb_g_entry.delete(0, tk.END)
    rgb_g_entry.insert(0, str(int(g)))

    rgb_b_entry.delete(0, tk.END)
    rgb_b_entry.insert(0, str(int(b)))

    rgb_status_var.set(
        f"RGB seleccionado: ({int(r)}, {int(g)}, {int(b)})"
    )

    eyedropper_status_var.set(
        f"Color tomado: RGB ({int(r)}, {int(g)}, {int(b)})"
    )

    # El cuentagotas se desactiva después de seleccionar.
    eyedropper_active = False
    eyedropper_button.configure(text="CUENTAGOTAS")
    camera_label.configure(cursor="")

    return True


# ============================================================
# CLICK DE CÁMARA
# ============================================================

def camera_click(event):
    global click_target_x, click_target_y

    # Primero tiene prioridad el cuentagotas.
    if pick_rgb_from_display(event):
        return

    if mode != "MANUAL":
        return

    if current_frame_for_picker is None:
        return

    h, w = current_frame_for_picker.shape[:2]

    if display_width <= 0 or display_height <= 0:
        return

    x = event.x * w / display_width
    y = event.y * h / display_height

    x = float(np.clip(x, 0, w - 1))
    y = float(np.clip(y, 0, h - 1))

    click_target_x = pixel_to_servo_x(x, w)

    click_target_y = pixel_to_servo_y(y, h) + 4
    click_target_y = float(np.clip(
        click_target_y,
        Y_MIN_ANGLE,
        Y_MAX_ANGLE
    ))

    reset_joystick()

    status_var.set(
        f"MANUAL — objetivo: "
        f"X {click_target_x:.1f}° / Y {click_target_y:.1f}°"
    )


# ============================================================
# MODO
# ============================================================

def set_mode(new_mode):
    global mode, click_target_x, click_target_y, prev_center

    mode = new_mode

    click_target_x = None
    click_target_y = None
    prev_center = None

    reset_joystick()

    if mode == "AUTO":
        mode_var.set("MODO: AUTOMÁTICO")
        status_var.set("Automático — buscando objetivo...")

    else:
        mode_var.set("MODO: MANUAL")
        status_var.set(
            "Manual — joystick o click sobre la cámara"
        )

        if serial_cmd:
            serial_cmd.send_manual(
                round(current_servo_x),
                round(current_servo_y)
            )


# ============================================================
# RGB
# ============================================================

def apply_rgb():
    global TARGET_COLOR_RGB
    global RGB_MARGIN_R, RGB_MARGIN_G, RGB_MARGIN_B

    try:
        r = int(rgb_r_entry.get())
        g = int(rgb_g_entry.get())
        b = int(rgb_b_entry.get())

        mr = int(rgb_margin_r_entry.get())
        mg = int(rgb_margin_g_entry.get())
        mb = int(rgb_margin_b_entry.get())

        if not all(0 <= value <= 255 for value in [r, g, b]):
            raise ValueError("RGB debe estar entre 0 y 255")

        if not all(value >= 0 for value in [mr, mg, mb]):
            raise ValueError("Los márgenes no pueden ser negativos")

        TARGET_COLOR_RGB = [r, g, b]

        RGB_MARGIN_R = mr
        RGB_MARGIN_G = mg
        RGB_MARGIN_B = mb

        rgb_status_var.set(
            f"RGB: ({r}, {g}, {b}) ± ({mr}, {mg}, {mb})"
        )

    except ValueError as e:
        rgb_status_var.set(f"⚠️ Valor inválido: {e}")


# ============================================================
# LOOP PRINCIPAL
# ============================================================

previous_frame_time = time.time()


def update_frame():
    global prev_center
    global current_servo_x, current_servo_y
    global click_target_x, click_target_y
    global previous_frame_time
    global photo_image
    global current_frame_for_picker
    global display_width, display_height

    ret, frame = cap.read()

    if not ret:
        status_var.set("❌ No se pudo leer la cámara")
        root.after(10, update_frame)
        return

    # --------------------------------------------------------
    # Resolución interna original
    # --------------------------------------------------------

    h, w = frame.shape[:2]

    scale = min(
        TARGET_WIDTH / w,
        TARGET_HEIGHT / h
    )

    frame = cv2.resize(
        frame,
        (int(w * scale), int(h * scale))
    )

    fh, fw = frame.shape[:2]

    # Este frame es el que se usa para RGB y para el cuentagotas.
    current_frame_for_picker = frame.copy()

    # --------------------------------------------------------
    # DETECCIÓN RGB
    # --------------------------------------------------------

    mask = build_rgb_mask(frame)

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

            if h_box == 0:
                continue

            aspect_ratio = w_box / float(h_box)

            if (1 - ASPECT_TOL) < aspect_ratio < (1 + ASPECT_TOL):
                if area > max_area:
                    best_cnt = cnt
                    max_area = area

    target_detected = best_cnt is not None

    # --------------------------------------------------------
    # CONTROL AUTOMÁTICO
    # --------------------------------------------------------

    if mode == "AUTO":

        if target_detected:
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

            frame_center_x = fw // 2
            frame_center_y = fh // 2

            error_x = smooth_center[0] - frame_center_x
            error_y = smooth_center[1] - frame_center_y

            max_error_x = frame_center_x

            target_servo_x = np.interp(
                error_x,
                [-max_error_x, max_error_x],
                [X_MAX_ANGLE, X_MIN_ANGLE]
            )

            max_error_y = 400

            target_servo_y = np.interp(
                error_y,
                [-max_error_y, max_error_y],
                [Y_MIN_ANGLE, Y_MAX_ANGLE]
            )

            target_servo_x = float(np.clip(
                target_servo_x,
                X_MIN_ANGLE,
                X_MAX_ANGLE
            ))

            target_servo_y = float(np.clip(
                target_servo_y,
                Y_MIN_ANGLE,
                Y_MAX_ANGLE
            ))

            current_servo_x = (
                current_servo_x * 0.7 +
                target_servo_x * 0.3
            )

            current_servo_y = (
                current_servo_y * 0.7 +
                target_servo_y * 0.3
            )

            clamp_servo_angles()

            if serial_cmd:
                serial_cmd.send_auto(
                    round(current_servo_x),
                    round(current_servo_y)
                )

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

            status_var.set(
                f"AUTO — objetivo detectado | "
                f"X {current_servo_x:.1f}° / "
                f"Y {current_servo_y:.1f}°"
            )

        else:
            prev_center = None

            if serial_cmd:
                serial_cmd.send_off()

            status_var.set(
                f"AUTO — sin objetivo | "
                f"X {current_servo_x:.1f}° / "
                f"Y {current_servo_y:.1f}°"
            )

    # --------------------------------------------------------
    # CONTROL MANUAL
    # --------------------------------------------------------

    else:

        now = time.time()
        dt = min(now - previous_frame_time, 0.1)

        if click_target_x is not None and click_target_y is not None:

            current_servo_x = move_towards(
                current_servo_x,
                click_target_x,
                CLICK_SPEED_X * dt
            )

            current_servo_y = move_towards(
                current_servo_y,
                click_target_y,
                CLICK_SPEED_Y * dt
            )

            if (
                abs(current_servo_x - click_target_x) < 0.05 and
                abs(current_servo_y - click_target_y) < 0.05
            ):
                current_servo_x = click_target_x
                current_servo_y = click_target_y
                click_target_x = None
                click_target_y = None

        elif joystick_active or abs(joystick_x) > 0.001 or abs(joystick_y) > 0.001:

            # Sentido X calibrado:
            # joystick derecha -> servo X disminuye
            current_servo_x -= joystick_x * MANUAL_SPEED_X * dt

            # Sentido Y:
            # joystick arriba -> servo Y disminuye
            current_servo_y += joystick_y * MANUAL_SPEED_Y * dt

        clamp_servo_angles()

        if serial_cmd:
            serial_cmd.send_manual(
                round(current_servo_x),
                round(current_servo_y)
            )

        if target_detected:
            x, y, w_box, h_box = cv2.boundingRect(best_cnt)

            cx = x + w_box // 2
            cy = y + h_box // 2

            cv2.rectangle(
                frame,
                (x, y),
                (x + w_box, y + h_box),
                (0, 165, 255),
                2
            )

            cv2.circle(
                frame,
                (cx, cy),
                5,
                (255, 255, 255),
                -1
            )

        if click_target_x is not None:
            status_var.set(
                f"MANUAL — moviendo a "
                f"X {click_target_x:.1f}° / "
                f"Y {click_target_y:.1f}°"
            )
        else:
            status_var.set(
                f"MANUAL — X {current_servo_x:.1f}° / "
                f"Y {current_servo_y:.1f}°"
            )

    # --------------------------------------------------------
    # RETÍCULA
    # --------------------------------------------------------

    aim_x = servo_to_pixel_x(current_servo_x, fw)
    aim_y = servo_to_pixel_y(current_servo_y, fh)

    center_x = fw // 2
    center_y = fh // 2

    cv2.line(
        frame,
        (aim_x - 22, aim_y),
        (aim_x + 22, aim_y),
        (255, 255, 255),
        2
    )

    cv2.line(
        frame,
        (aim_x, aim_y - 22),
        (aim_x, aim_y + 22),
        (255, 255, 255),
        2
    )

    cv2.circle(
        frame,
        (aim_x, aim_y),
        8,
        (255, 255, 255),
        2
    )

    cv2.circle(
        frame,
        (center_x, center_y),
        3,
        (0, 255, 0),
        -1
    )

    # --------------------------------------------------------
    # INFORMACIÓN
    # --------------------------------------------------------

    cv2.putText(
        frame,
        f"Modo: {mode}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Servo X: {current_servo_x:.1f}",
        (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )

    cv2.putText(
        frame,
        f"Servo Y: {current_servo_y:.1f}",
        (10, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )

    # --------------------------------------------------------
    # FPS
    # --------------------------------------------------------

    curr_time = time.time()

    fps = int(
        1 / (curr_time - previous_frame_time)
    ) if curr_time != previous_frame_time else 0

    previous_frame_time = curr_time

    cv2.putText(
        frame,
        f"FPS: {fps}",
        (fw - 130, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    # --------------------------------------------------------
    # MOSTRAR IMAGEN
    # --------------------------------------------------------
    # IMPORTANTE:
    # El Label recibe EXACTAMENTE el tamaño de esta imagen.
    # Ya no existe un cuadro mayor que la imagen que pueda
    # introducir un offset en los clicks.

    display_width = fw
    display_height = fh

    display_frame = frame

    display_frame = cv2.cvtColor(
        display_frame,
        cv2.COLOR_BGR2RGB
    )

    image = Image.fromarray(display_frame)
    photo_image = ImageTk.PhotoImage(image=image)

    camera_label.configure(
        image=photo_image,
        width=display_width,
        height=display_height
    )

    camera_label.image = photo_image

    servo_x_var.set(f"{current_servo_x:.1f}°")
    servo_y_var.set(f"{current_servo_y:.1f}°")

    root.after(1, update_frame)


# ============================================================
# CIERRE
# ============================================================

def close_app():
    print("\n🛑 Cerrando...")

    try:
        cap.release()
    except Exception:
        pass

    if serial_cmd:
        serial_cmd.stop()

    root.destroy()


# ============================================================
# INTERFAZ
# ============================================================

root = tk.Tk()
root.title("Sistema de Tracking — Torreta")
root.geometry("1450x950")
root.minsize(1100, 750)

root.protocol("WM_DELETE_WINDOW", close_app)

root.bind("<KeyPress-q>", lambda event: close_app())
root.bind("<Escape>", lambda event: close_app())

main = ttk.Frame(root, padding=10)
main.pack(fill="both", expand=True)

# ------------------------------------------------------------
# CÁMARA
# ------------------------------------------------------------

camera_frame = ttk.LabelFrame(
    main,
    text="Cámara / Dirección de apuntado",
    padding=5
)

camera_frame.pack(
    side="left",
    fill="both",
    expand=True,
    padx=(0, 10)
)

camera_label = tk.Label(
    camera_frame,
    text="Inicializando cámara...",
    bg="black",
    fg="white",
    bd=0,
    highlightthickness=0
)

camera_label.pack(
    anchor="nw"
)

camera_label.bind(
    "<Button-1>",
    camera_click
)

# ------------------------------------------------------------
# PANEL DERECHO
# ------------------------------------------------------------

control_frame = ttk.Frame(main, width=300)
control_frame.pack(
    side="right",
    fill="y"
)

control_frame.pack_propagate(False)

ttk.Label(
    control_frame,
    text="CONTROL",
    font=("Arial", 16, "bold")
).pack(pady=(0, 8))

mode_var = tk.StringVar(value="MODO: AUTOMÁTICO")

ttk.Label(
    control_frame,
    textvariable=mode_var,
    font=("Arial", 12, "bold")
).pack(pady=(0, 8))

mode_buttons = ttk.Frame(control_frame)
mode_buttons.pack(fill="x", pady=(0, 12))

ttk.Button(
    mode_buttons,
    text="AUTOMÁTICO",
    command=lambda: set_mode("AUTO")
).pack(
    side="left",
    fill="x",
    expand=True,
    padx=(0, 4)
)

ttk.Button(
    mode_buttons,
    text="MANUAL",
    command=lambda: set_mode("MANUAL")
).pack(
    side="left",
    fill="x",
    expand=True,
    padx=(4, 0)
)

status_var = tk.StringVar(
    value="Automático — buscando objetivo..."
)

ttk.Label(
    control_frame,
    textvariable=status_var,
    wraplength=280,
    justify="left"
).pack(
    fill="x",
    pady=(0, 15)
)

# ------------------------------------------------------------
# SERVOS
# ------------------------------------------------------------

angle_frame = ttk.LabelFrame(
    control_frame,
    text="Servos",
    padding=8
)

angle_frame.pack(fill="x", pady=(0, 12))

ttk.Label(
    angle_frame,
    text="X:"
).grid(row=0, column=0, sticky="w")

servo_x_var = tk.StringVar(value=f"{CENTER_X:.1f}°")

ttk.Label(
    angle_frame,
    textvariable=servo_x_var,
    font=("Arial", 11, "bold")
).grid(row=0, column=1, sticky="e")

ttk.Label(
    angle_frame,
    text="Y:"
).grid(row=1, column=0, sticky="w")

servo_y_var = tk.StringVar(value=f"{CENTER_Y:.1f}°")

ttk.Label(
    angle_frame,
    textvariable=servo_y_var,
    font=("Arial", 11, "bold")
).grid(row=1, column=1, sticky="e")

angle_frame.columnconfigure(1, weight=1)

# ------------------------------------------------------------
# JOYSTICK
# ------------------------------------------------------------

joystick_frame = ttk.LabelFrame(
    control_frame,
    text="Joystick manual",
    padding=5
)

joystick_frame.pack(fill="x", pady=(0, 12))

joystick_canvas = tk.Canvas(
    joystick_frame,
    width=JOYSTICK_SIZE,
    height=JOYSTICK_SIZE,
    highlightthickness=0,
    bg="#202020"
)

joystick_canvas.pack()

joystick_canvas.create_oval(
    JOYSTICK_CENTER - JOYSTICK_RADIUS,
    JOYSTICK_CENTER - JOYSTICK_RADIUS,
    JOYSTICK_CENTER + JOYSTICK_RADIUS,
    JOYSTICK_CENTER + JOYSTICK_RADIUS,
    outline="white",
    width=2
)

joystick_canvas.create_line(
    JOYSTICK_CENTER - JOYSTICK_RADIUS,
    JOYSTICK_CENTER,
    JOYSTICK_CENTER + JOYSTICK_RADIUS,
    JOYSTICK_CENTER,
    fill="gray"
)

joystick_canvas.create_line(
    JOYSTICK_CENTER,
    JOYSTICK_CENTER - JOYSTICK_RADIUS,
    JOYSTICK_CENTER,
    JOYSTICK_CENTER + JOYSTICK_RADIUS,
    fill="gray"
)

joystick_knob = joystick_canvas.create_oval(
    JOYSTICK_CENTER - KNOB_RADIUS,
    JOYSTICK_CENTER - KNOB_RADIUS,
    JOYSTICK_CENTER + KNOB_RADIUS,
    JOYSTICK_CENTER + KNOB_RADIUS,
    outline="white",
    width=2
)

joystick_canvas.bind("<ButtonPress-1>", joystick_press)
joystick_canvas.bind("<B1-Motion>", joystick_drag)
joystick_canvas.bind("<ButtonRelease-1>", joystick_release)

# ------------------------------------------------------------
# RGB
# ------------------------------------------------------------

rgb_frame = ttk.LabelFrame(
    control_frame,
    text="Detección RGB",
    padding=8
)

rgb_frame.pack(fill="x", pady=(0, 12))

ttk.Label(rgb_frame, text="R").grid(row=0, column=0)
ttk.Label(rgb_frame, text="G").grid(row=0, column=1)
ttk.Label(rgb_frame, text="B").grid(row=0, column=2)

rgb_r_entry = ttk.Entry(rgb_frame, width=7)
rgb_g_entry = ttk.Entry(rgb_frame, width=7)
rgb_b_entry = ttk.Entry(rgb_frame, width=7)

rgb_r_entry.grid(row=1, column=0, padx=2)
rgb_g_entry.grid(row=1, column=1, padx=2)
rgb_b_entry.grid(row=1, column=2, padx=2)

rgb_r_entry.insert(0, str(TARGET_COLOR_RGB[0]))
rgb_g_entry.insert(0, str(TARGET_COLOR_RGB[1]))
rgb_b_entry.insert(0, str(TARGET_COLOR_RGB[2]))

ttk.Label(
    rgb_frame,
    text="Margen"
).grid(
    row=2,
    column=0,
    columnspan=3,
    pady=(7, 2)
)

rgb_margin_r_entry = ttk.Entry(rgb_frame, width=7)
rgb_margin_g_entry = ttk.Entry(rgb_frame, width=7)
rgb_margin_b_entry = ttk.Entry(rgb_frame, width=7)

rgb_margin_r_entry.grid(row=3, column=0, padx=2)
rgb_margin_g_entry.grid(row=3, column=1, padx=2)
rgb_margin_b_entry.grid(row=3, column=2, padx=2)

rgb_margin_r_entry.insert(0, str(RGB_MARGIN_R))
rgb_margin_g_entry.insert(0, str(RGB_MARGIN_G))
rgb_margin_b_entry.insert(0, str(RGB_MARGIN_B))

eyedropper_button = ttk.Button(
    rgb_frame,
    text="CUENTAGOTAS",
    command=toggle_eyedropper
)

eyedropper_button.grid(
    row=4,
    column=0,
    columnspan=3,
    sticky="ew",
    pady=(8, 4)
)

eyedropper_status_var = tk.StringVar(value="")

ttk.Label(
    rgb_frame,
    textvariable=eyedropper_status_var,
    wraplength=260,
    justify="center"
).grid(
    row=5,
    column=0,
    columnspan=3
)

ttk.Button(
    rgb_frame,
    text="Aplicar RGB",
    command=apply_rgb
).grid(
    row=6,
    column=0,
    columnspan=3,
    sticky="ew",
    pady=(7, 3)
)

rgb_status_var = tk.StringVar(
    value=(
        f"RGB: {tuple(TARGET_COLOR_RGB)} ± "
        f"({RGB_MARGIN_R}, {RGB_MARGIN_G}, {RGB_MARGIN_B})"
    )
)

ttk.Label(
    rgb_frame,
    textvariable=rgb_status_var,
    wraplength=260,
    justify="center"
).grid(
    row=7,
    column=0,
    columnspan=3
)

# ------------------------------------------------------------
# AYUDA
# ------------------------------------------------------------

help_frame = ttk.LabelFrame(
    control_frame,
    text="Controles",
    padding=8
)

help_frame.pack(fill="x")

ttk.Label(
    help_frame,
    text=(
        "MANUAL:\n"
        "• Arrastra el joystick para mover.\n"
        "• Click en la cámara = apunta.\n"
        "• Cuentagotas = toma RGB del punto elegido.\n"
        "• Suelta el joystick = detiene.\n\n"
        "AUTO:\n"
        "• El objetivo RGB controla los servos.\n\n"
        "Q / ESC = salir"
    ),
    justify="left",
    wraplength=270
).pack()

# ============================================================
# INICIO
# ============================================================

print("\n🎥 Iniciando interfaz...")
print("   AUTO   = tracking RGB")
print("   MANUAL = joystick + click")
print("   RGB    = cuentagotas")
print("   Q/ESC  = salir\n")

root.after(1, update_frame)
root.mainloop()