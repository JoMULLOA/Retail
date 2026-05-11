@echo off
cd /d "%~dp0"
echo ========================================
echo  RetailVision Pilot — Instalacion CPU
echo ========================================
echo.

REM Check Python version
python --version 2>nul || (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ desde python.org
    pause
    exit /b 1
)

REM Create virtual environment
if not exist .venv (
    echo [1/3] Creando entorno virtual...
    python -m venv .venv
)

echo [2/3] Activando entorno virtual...
call .venv\Scripts\activate.bat

echo [3/3] Instalando dependencias...
pip install -r requirements.txt

echo.
echo ========================================
echo  Instalacion completada.
echo  Para ejecutar: run.bat
echo ========================================
pause
