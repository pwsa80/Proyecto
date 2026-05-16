import cv2
import numpy as np
import time

# ================= ⚙️ CONFIGURACIÓN EDITABLE =================
# 🔄 INTERRUPTOR DE CÁMARA (True = IP Celular | False = Webcam predeterminada)
USE_IP_CAMERA = False

if USE_IP_CAMERA:
    CAMERA_SOURCE = "http://192.168.1.4:8080/video"
    print("📱 Modo: CÁMARA IP (Celular)")
else:
    CAMERA_SOURCE = 0  # Cambia a 1, 2... si tienes múltiples webcams
    print("💻 Modo: WEBCAM PREDETERMINADA")

# 📐 Dimensiones objetivo
TARGET_WIDTH = 1000
TARGET_HEIGHT = 800

# 🎨 Rango HSV (modifica aquí sin reiniciar la app)
H_BASE = 0          # Tono base (0-179). 0 = rojo/naranja extremo
H_MARGIN = 12       # Margen de error +/- para el canal H
S_MIN = 180         # Saturación mínima (filtra colores lavados)
S_MAX = 255         # Saturación máxima
V_MIN = 90          # Brillo mínimo (ignora sombras profundas)
V_MAX = 255         # Brillo máximo

# 🔍 Filtros de detección
MIN_AREA = 600      # Área mínima en píxeles (ignora ruido pequeño)
ASPECT_TOL = 0.3    # Tolerancia de forma (0.3 = 70%-130% relación ancho/alto)

# 🎨 Estilo visual
BOX_COLOR = (0, 165, 255)
LABEL_TEXT = "OBJETIVO"
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.6
FONT_THICKNESS = 2
# ============================================================

WIN_NAME = "🔍 Detección en Tiempo Real"
cap = cv2.VideoCapture(CAMERA_SOURCE)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 🚀 Reduce latencia mostrando frame más reciente

if not cap.isOpened():
    print(f"❌ No se pudo abrir la fuente: {CAMERA_SOURCE}")
    print("💡 Verifica: 1) Mismo Wi-Fi / 2) App corriendo / 3) Puertos libres")
    exit()

prev_time = time.time()
print("✅ Conectado. Presiona 'q' para salir.\n")

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️ Stream perdido o cámara desconectada.")
        break

    # 📐 Redimensionar manteniendo proporción
    h_orig, w_orig = frame.shape[:2]
    scale = min(TARGET_WIDTH / w_orig, TARGET_HEIGHT / h_orig)
    new_w, new_h = int(w_orig * scale), int(h_orig * scale)
    frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # ⏱️ FPS
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time) if curr_time != prev_time else 0
    prev_time = curr_time

    # 🎨 Procesamiento HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_bound = np.array([np.clip(H_BASE - H_MARGIN, 0, 179), S_MIN, V_MIN])
    upper_bound = np.array([np.clip(H_BASE + H_MARGIN, 0, 179), S_MAX, V_MAX])
    mask = cv2.inRange(hsv, lower_bound, upper_bound)

    # 🧼 Limpieza morfológica
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # 🔍 Contornos
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 🖼️ Dibujado elegante
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > MIN_AREA:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h)

            if (1 - ASPECT_TOL) < aspect_ratio < (1 + ASPECT_TOL):
                cv2.rectangle(frame, (x, y), (x + w, y + h), BOX_COLOR, 3)

                (tw, th), _ = cv2.getTextSize(LABEL_TEXT, FONT, FONT_SCALE, FONT_THICKNESS)
                cv2.rectangle(frame, (x, y - th - 10), (x + tw + 8, y), BOX_COLOR, -1)
                cv2.putText(frame, LABEL_TEXT, (x + 4, y - 5), FONT, FONT_SCALE, (0, 0, 0), 2)

                cv2.circle(frame, (x + w//2, y + h//2), 4, (255, 255, 255), -1)

    # 📊 Info en pantalla
    cv2.putText(frame, f"FPS: {int(fps)} | H: {H_BASE}±{H_MARGIN}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow(WIN_NAME, frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()