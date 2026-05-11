@echo off
cd /d "%~dp0"
echo ========================================
echo  RetailVision Pilot — Instalacion CUDA
echo ========================================
echo  Requiere: NVIDIA GPU + drivers CUDA 12.4+
echo.

REM Check Python version
python --version 2>nul || (
    echo [ERROR] Python no encontrado. Instala Python 3.10 - 3.12 desde python.org
    echo (CUDA no funciona con Python 3.13+ aun)
    pause
    exit /b 1
)

REM Create virtual environment
if not exist .venv (
    echo [1/4] Creando entorno virtual...
    python -m venv .venv
)

echo [2/4] Activando entorno virtual...
call .venv\Scripts\activate.bat

echo [3/4] Instalando PyTorch con CUDA 12.4...
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

echo [4/4] Instalando resto de dependencias...
pip install -r requirements.txt

echo.
echo ========================================
echo  Instalacion CUDA completada.
echo  Para ejecutar: run.bat
echo ========================================
pause
