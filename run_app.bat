@echo off
echo ===================================================
echo    SISTEMA DE CONTROL DE MUESTRAS - INICIANDO
echo ===================================================
cd /d "%~dp0"

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Por favor instale Python 3.10+
    pause
    exit /b
)

:: Create Venv if missing
if not exist "venv" (
    echo [INFO] Creando entorno virtual (primera vez)...
    python -m venv venv
)

:: Activate Venv
call venv\Scripts\activate

:: Install requirements
echo [INFO] Verificando dependencias...
pip install -q -r requirements.txt

:: Launch Browser
echo [INFO] Abriendo aplicacion en el navegador...
start http://127.0.0.1:8000

:: Start Server
echo [INFO] Iniciando servidor...
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000

pause
