@echo off
cd /d "%~dp0"
echo ========================================
echo   RetailVision Pilot
echo ========================================
echo.

REM Auto-detect virtual environment
if exist .venv312\Scripts\python.exe (
    echo [OK] Python 3.12 + CUDA
    .venv312\Scripts\python.exe app.py
) else if exist .venv\Scripts\python.exe (
    call .venv\Scripts\activate.bat
    echo [OK] Entorno virtual activado
    python app.py
) else (
    echo [!] Usando Python del sistema (sin virtualenv)
    echo     Si falta algo: corre install.bat o install_cuda.bat
    echo.
    python app.py
)

pause
