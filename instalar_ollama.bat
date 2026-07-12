@echo off
setlocal

cd /d "%~dp0"
title Instalar Ollama (gratis local)

set "OLLAMA_EXE="
where ollama >nul 2>&1
if not errorlevel 1 set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_EXE if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles(x86)%\Ollama\ollama.exe"

if not defined OLLAMA_EXE (
    echo Ollama no esta instalado. Intentando instalar con winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo No se encontro winget en este Windows.
        echo Instala Ollama manualmente desde: https://ollama.com/download/windows
        pause
        exit /b 1
    )

    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo Fallo al instalar Ollama con winget.
        echo Prueba instalacion manual: https://ollama.com/download/windows
        pause
        exit /b 1
    )
)

if not defined OLLAMA_EXE (
    where ollama >nul 2>&1
    if not errorlevel 1 set "OLLAMA_EXE=ollama"
)
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_EXE if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles(x86)%\Ollama\ollama.exe"

if not defined OLLAMA_EXE (
    echo Ollama parece instalado, pero no se encuentra el ejecutable.
    echo Cierra esta ventana y abre una nueva terminal.
    pause
    exit /b 1
)

set "MODEL=llama3.2:1b"
echo.
echo Iniciando servicio Ollama...
start "" /min cmd /c "\"%OLLAMA_EXE%\" serve"
timeout /t 3 >nul

echo Descargando modelo %MODEL% (solo la primera vez puede tardar)...
"%OLLAMA_EXE%" pull %MODEL%
if errorlevel 1 (
    echo No se pudo descargar el modelo.
    pause
    exit /b 1
)

echo.
echo Listo. Ollama y el modelo estan preparados.
echo Ya puedes usar iniciar_chatbot.bat
pause
