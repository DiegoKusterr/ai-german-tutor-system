@echo off
setlocal
cd /d "%~dp0"
title Chatbot Aleman - Local

if not exist ".venv\Scripts\python.exe" (
    echo No existe .venv. Prepare el entorno manualmente antes de iniciar.
    echo Comandos de preparacion: py -3.11 -m venv .venv
    echo Despues: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
"%PYTHON_EXE%" -c "import fastapi, uvicorn, dotenv" >nul 2>&1
if errorlevel 1 (
    echo Faltan dependencias. Instale requirements.txt manualmente.
    exit /b 1
)

echo Inicio local: http://127.0.0.1:8000
echo Ollama y los modelos deben estar preparados antes del inicio.
echo LAN requiere --lan --host 0.0.0.0. HTTPS local requiere --https.
echo El acceso publico se habilita por separado en run_public_tunnel.py con --public y --demo-data-dir.
"%PYTHON_EXE%" run_local_servers.py %*
exit /b %errorlevel%
