# ============================================================
# RetailVision Pilot — Docker (GPU / CUDA)
# ============================================================
# Basado en PyTorch oficial con CUDA 12.4 + cuDNN 9
#
# Build:   docker compose build
# Run:     docker compose up
# Abrir:   http://localhost:8000
# ============================================================

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

LABEL description="RetailVision Pilot — YOLO Person Detection + Web Streaming"

# Evita prompts de tzdata
ENV DEBIAN_FRONTEND=noninteractive

# Instala system deps para OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia requirements primero (cachea capa de pip)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del proyecto
COPY . .

# Crea directorio para uploads
RUN mkdir -p uploads

# Puerto web
EXPOSE 8000

# Corre con CUDA, suprime warnings de numpy
CMD ["python", "-W", "ignore", "app.py"]
