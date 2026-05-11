"""
RetailVision Pilot
==================
Detección de personas en videos usando YOLOv11 con streaming
MJPEG en tiempo real vía navegador web.

Requiere:
    Python 3.10 - 3.12 (CUDA requiere 3.10 - 3.12)
    NVIDIA GPU + CUDA 12.4 (opcional, para aceleración)

Instalación rápida (CPU - cualquier PC):
    pip install -r requirements.txt
    python app.py
    -> Abrir http://127.0.0.1:8000

Instalación con GPU (CUDA):
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
    pip install -r requirements.txt
    python app.py

Windows: usa install.bat (CPU) o install_cuda.bat (GPU)
"""

import os
import cv2
import time
import uuid
import threading
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO
import torch
import uvicorn

# ═══════════════════════════════════════════════════════════
# Configuración
# ═══════════════════════════════════════════════════════════

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MODEL_NAME = "yolo11s.pt"       # nano→rápido, small→balance, medium→preciso
CONFIDENCE = 0.45               # mínimo de confianza
PERSON_CLASS = 0                # COCO: 0 = persona
JPEG_QUALITY = 82               # calidad streaming
MAX_FRAME_SIZE = 1920           # máximo ancho de frame
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# ═══════════════════════════════════════════════════════════
# Device
# ═══════════════════════════════════════════════════════════

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
if torch.cuda.is_available():
    print(f"  🎮 GPU: {torch.cuda.get_device_name(0)}")
    # Warm-up: corre una inferencia vacía para que CUDA compile kernels
    print("  🔥 Warming up CUDA...")
else:
    print("  ⚠️  CUDA no disponible — usando CPU")

# ═══════════════════════════════════════════════════════════
# Modelo
# ═══════════════════════════════════════════════════════════

print(f"\n🚀 Cargando {MODEL_NAME}...")
model = YOLO(MODEL_NAME)

# Mover explícitamente al dispositivo correcto
if DEVICE != "cpu":
    model.to(DEVICE)

total_params = sum(p.numel() for p in model.model.parameters()
                  ) if hasattr(model, 'model') else 0
print(f"✅ Modelo cargado. Parámetros: {total_params:,}")
print(f"📡 Dispositivo: {model.device}\n")

# Warm-up: tiny inference to initialize CUDA kernels
if DEVICE != "cpu":
    import numpy as np
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    model.predict(dummy, verbose=False, device=DEVICE)
    print("  🔥 CUDA warmed up\n")
    del dummy

# ═══════════════════════════════════════════════════════════
# Estado (thread-safe)
# ═══════════════════════════════════════════════════════════

_state_lock = threading.Lock()
_state = {
    "video_path": None,
    "video_name": "",
    "processing": False,
    "device": DEVICE,
    "total_frames": 0,
    "total_detections": 0,
    "max_persons": 0,
    "current_persons": 0,
    "fps": 0.0,
    "progress": 0.0,
}


def get_state():
    with _state_lock:
        return dict(_state)


def set_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)


def reset_state(**kwargs):
    with _state_lock:
        _state.clear()
        _state.update(**kwargs)


# ═══════════════════════════════════════════════════════════
# App
# ═══════════════════════════════════════════════════════════

app = FastAPI(title="RetailVision Pilot")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def is_allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def resize_if_needed(frame, max_w=MAX_FRAME_SIZE):
    h, w = frame.shape[:2]
    if w > max_w:
        scale = max_w / w
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(frame, (new_w, new_h))
    return frame


def add_overlay(frame, person_count: int, fps: float, progress: float):
    """Agrega info superpuesta: conteo, FPS, progreso, dispositivo."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cur_device = get_state()["device"]

    # ── Barra superior ──
    cv2.rectangle(overlay, (0, 0), (w, 64), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    cv2.putText(frame, f"Personas: {person_count}", (20, 44),
                cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 255, 0), 2)
    cv2.putText(frame, f"{fps:.1f} FPS", (w - 160, 44),
                cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 255, 0), 2)

    # ── Device indicator ──
    dev_label = cur_device.upper()
    dev_color = (0, 255, 0) if "cuda" in cur_device else (100, 100, 100)
    (tw, th), _ = cv2.getTextSize(dev_label, cv2.FONT_HERSHEY_DUPLEX, 0.6, 1)
    cv2.rectangle(frame, (w - tw - 14, 68), (w - 8, 68 + th + 10), (20, 20, 20), -1)
    cv2.putText(frame, dev_label, (w - tw - 10, 68 + th + 4),
                cv2.FONT_HERSHEY_DUPLEX, 0.6, dev_color, 1)

    # ── Barra de progreso ──
    bar_w = w - 40
    bar_h = 8
    bar_x, bar_y = 20, h - 30
    filled = int(bar_w * progress)

    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                  (40, 40, 40), -1)
    if filled > 0:
        color = (0, 255, 100) if progress < 1.0 else (0, 200, 255)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + filled, bar_y + bar_h),
                      color, -1)

    cv2.putText(frame, f"{progress * 100:.0f}%", (w - 80, h - 48),
                cv2.FONT_HERSHEY_DUPLEX, 0.7, (200, 200, 200), 1)

    return frame


# ═══════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    if not is_allowed(file.filename):
        raise HTTPException(400,
                            f"Formato no soportado. Usa: {', '.join(ALLOWED_EXTENSIONS)}")

    # Guardar con nombre único
    ext = Path(file.filename).suffix
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Archivo vacío")

    with open(dest, "wb") as f:
        f.write(content)

    reset_state(
        video_path=str(dest),
        video_name=file.filename,
        processing=True,
        device=DEVICE,
        total_frames=0,
        total_detections=0,
        max_persons=0,
        current_persons=0,
        fps=0.0,
        progress=0.0,
    )

    return {
        "status": "ok",
        "filename": file.filename,
        "size_mb": round(len(content) / (1024 * 1024), 2),
    }


@app.get("/stats")
async def get_stats():
    return JSONResponse(get_state())


def generate_frames(video_path: str):
    """
    Generador sync MJPEG: lee video, corre YOLO, entrega frames anotados.
    Starlette lo ejecuta en un thread pool automáticamente (no bloquea el event loop).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] No se pudo abrir: {video_path}")
        set_state(processing=False)
        return

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    frame_idx = 0
    t_start = time.perf_counter()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1

            # Resize si es muy grande (mejora performance)
            frame = resize_if_needed(frame)

            # ── Inferencia YOLO (todo en este mismo thread) ──
            results = model(frame, classes=[PERSON_CLASS],
                            conf=CONFIDENCE, verbose=False)

            boxes_data = results[0].boxes
            person_count = len(boxes_data)

            # ── Extraer datos a CPU / Python plano (evita CUDA cross-thread) ──
            dets = []
            if boxes_data is not None and person_count > 0:
                xyxy = boxes_data.xyxy.cpu().numpy() if boxes_data.xyxy.is_cuda else boxes_data.xyxy.numpy()
                confs = boxes_data.conf.cpu().numpy() if boxes_data.conf.is_cuda else boxes_data.conf.numpy()
                for i in range(person_count):
                    x1, y1, x2, y2 = map(int, xyxy[i])
                    dets.append({"bbox": (x1, y1, x2, y2), "conf": float(confs[i])})

            # ── Anotaciones en el frame ──
            annotated = frame.copy()
            colors = [(0, 255, 0), (0, 200, 255), (255, 100, 0), (0, 150, 255)]
            for i, det in enumerate(dets):
                x1, y1, x2, y2 = det["bbox"]
                conf = det["conf"]
                color = colors[i % len(colors)]

                # Borde grueso
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
                # Relleno semitransparente
                overlay = annotated.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
                cv2.addWeighted(overlay, 0.08, annotated, 0.92, 0, annotated)

                # Label con fondo sólido
                label = f"Persona {conf:.0%}"
                (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.6, 2)
                label_y = y1 - 10 if y1 > 28 else y2 + lh + 10
                cv2.rectangle(annotated, (x1, label_y - lh - 6),
                              (x1 + lw + 8, label_y + 4), color, -1)
                cv2.putText(annotated, label, (x1 + 4, label_y - 2),
                            cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 2)

            # ── Métricas ──
            elapsed = time.perf_counter() - t_start
            fps = frame_idx / elapsed if elapsed > 0 else 0
            progress = frame_idx / total

            set_state(
                total_frames=frame_idx,
                total_detections=get_state()["total_detections"] + person_count,
                max_persons=max(get_state()["max_persons"], person_count),
                current_persons=person_count,
                fps=fps,
                progress=min(progress, 1.0),
            )

            # ── Overlay ──
            add_overlay(annotated, person_count, fps, min(progress, 1.0))

            # ── Codificar JPEG ──
            ret_code, jpeg = cv2.imencode(
                ".jpg", annotated,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if not ret_code:
                continue

            # ── Yield MJPEG part (formato correcto: \r\n al final, NO \r\n\r\n) ──
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                jpeg.tobytes() + b"\r\n"
            )

        print(f"[INFO] Video procesado: {frame_idx} frames, "
              f"{get_state()['total_detections']} detecciones")

    except Exception as e:
        print(f"[ERROR] Streaming error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cap.release()
        set_state(processing=False, progress=1.0)
        try:
            os.remove(video_path)
        except OSError:
            pass


@app.get("/video_feed")
async def video_feed():
    s = get_state()
    if not s["video_path"] or not os.path.exists(s["video_path"]):
        return HTMLResponse("No video uploaded", status_code=404)

    return StreamingResponse(
        generate_frames(s["video_path"]),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ═══════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    url = "http://127.0.0.1:8000"
    print(f"🔗 Abre {url} en tu navegador")

    # Abre el navegador después de 1.5s para que el server alcance a arrancar
    def _open_browser():
        import time as _t
        _t.sleep(1.5)
        import webbrowser
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
