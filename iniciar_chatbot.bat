@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"
title Chatbot Aleman - Lanzador unico

set "PYTHON_EXE="
set "PUBLIC_TUNNEL_AVAILABLE=0"
set "CLOUDFLARED_EXE="

echo [1/5] Preparando entorno Python del proyecto...
call :ensure_repo_venv
if errorlevel 1 exit /b 1

call :read_env CHAT_PROVIDER PROVIDER ollama
call :read_env OLLAMA_MODEL OLLAMA_MODEL llama3.2:3b
call :read_env OLLAMA_BASE_URL OLLAMA_BASE_URL http://127.0.0.1:11434
set "PROVIDER=!PROVIDER:"=!"
set "PROVIDER=!PROVIDER:'=!"
set "OLLAMA_MODEL=!OLLAMA_MODEL:"=!"
set "OLLAMA_MODEL=!OLLAMA_MODEL:'=!"
set "OLLAMA_BASE_URL=!OLLAMA_BASE_URL:"=!"
set "OLLAMA_BASE_URL=!OLLAMA_BASE_URL:'=!"

if /I "%PROVIDER%"=="auto" set "PROVIDER=ollama"

if /I "%PROVIDER%"=="ollama" (
    echo.
    echo [2/5] Verificando Ollama y el modelo conversacional...
    set "OLLAMA_REQUIRED=1"
    call :ensure_ollama
    if errorlevel 1 exit /b 1
) else (
    echo.
    echo [2/5] Ollama omitido porque CHAT_PROVIDER=%PROVIDER%.
)

echo.
echo [3/5] Instalando dependencias Python en el entorno del proyecto...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Error al instalar dependencias en el entorno virtual del proyecto.
    echo Python usado: %PYTHON_EXE%
    pause
    exit /b 1
)

echo.
echo [4/5] Comprobando enlace publico HTTPS gratis...
call :ensure_cloudflared_optional

echo.
echo [5/5] Detectando IP local y lanzando la app...
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LOCAL_IP=%%I"
if "%LOCAL_IP%"=="" set "LOCAL_IP=127.0.0.1"

set "URL_PC=http://127.0.0.1:8000"
set "URL_MOVIL=http://%LOCAL_IP%:8000"
set "URL_MOVIL_HTTPS=https://%LOCAL_IP%:8443"
set "URL_CERT=http://%LOCAL_IP%:8000/local-ca.crt"

echo.
echo Python del proyecto: %PYTHON_EXE%
echo Proveedor esperado: %PROVIDER%
if /I "%PROVIDER%"=="ollama" (
    echo Modelo Ollama configurado: %OLLAMA_MODEL%
    echo Ollama URL: %OLLAMA_BASE_URL%
)
echo En el PC:     %URL_PC%
echo En el movil:  %URL_MOVIL%
echo En el movil seguro: %URL_MOVIL_HTTPS%
echo Certificado movil:  %URL_CERT%
echo.
if "%PUBLIC_TUNNEL_AVAILABLE%"=="1" (
    echo Este lanzador abrira el navegador solo cuando el backend ya este listo.
    echo Ademas intentara crear una URL publica HTTPS gratis.
) else (
    echo Este lanzador abrira el navegador solo cuando el backend ya este listo.
    echo No se pudo preparar cloudflared automaticamente.
    echo La app seguira funcionando en local.
    echo Para micro en movil sin certificado, instala cloudflared gratis y vuelve a abrir este lanzador:
    echo winget install --id Cloudflare.cloudflared
    echo.
    echo Fallback local para micro en movil:
    echo 1. Abre %URL_CERT% una vez y instala el certificado local.
    echo 2. Abre despues %URL_MOVIL_HTTPS%
)
echo.

set "CHAT_PROVIDER=%PROVIDER%"
set "OLLAMA_MODEL=%OLLAMA_MODEL%"
set "OLLAMA_BASE_URL=%OLLAMA_BASE_URL%"

if "%PUBLIC_TUNNEL_AVAILABLE%"=="1" (
    "%PYTHON_EXE%" run_public_tunnel.py --host 0.0.0.0 --http-port 8000 --https-port 8443 --local-ip "%LOCAL_IP%" --open-url "%URL_PC%" --startup-timeout 90 --expected-provider "%PROVIDER%"
) else (
    "%PYTHON_EXE%" run_local_servers.py --host 0.0.0.0 --http-port 8000 --https-port 8443 --local-ip "%LOCAL_IP%" --open-url "%URL_PC%" --startup-timeout 90 --expected-provider "%PROVIDER%"
)

if errorlevel 1 (
    echo.
    echo Arranque fallido. Revise el diagnostico anterior y vuelva a intentar.
    pause
    exit /b 1
)

echo.
echo El servidor se ha detenido.
pause
exit /b 0

:ensure_repo_venv
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    echo [Python] Usando entorno virtual existente: %PYTHON_EXE%
    exit /b 0
)

echo [Python] No existe .venv. Creando entorno virtual local...
where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv .venv >nul 2>&1
    if errorlevel 1 py -3 -m venv .venv
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo No se encontro un Python base para crear .venv.
        echo Instale Python 3.11+ y vuelva a ejecutar iniciar_chatbot.bat.
        pause
        exit /b 1
    )
    python -m venv .venv
)

if errorlevel 1 (
    echo No se pudo crear el entorno virtual del proyecto en .venv.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Se creo .venv pero no aparece .venv\Scripts\python.exe.
    pause
    exit /b 1
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
echo [Python] Entorno virtual creado: %PYTHON_EXE%
exit /b 0

:read_env
set "KEY=%~1"
set "TARGET=%~2"
set "DEFAULT=%~3"
set "RAW="
for /f "tokens=1,* delims==" %%A in ('findstr /B /C:"%KEY%=" ".env" 2^>nul') do (
    if /I "%%A"=="%KEY%" set "RAW=%%B"
)
if defined RAW (
    set "RAW=!RAW:"=!"
    set "RAW=!RAW:'=!"
    set "%TARGET%=!RAW!"
) else (
    set "%TARGET%=%DEFAULT%"
)
exit /b 0

:probe_ollama
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%OLLAMA_BASE_URL%/api/tags' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:ensure_cloudflared_optional
call :find_cloudflared
if defined CLOUDFLARED_EXE (
    set "PUBLIC_TUNNEL_AVAILABLE=1"
    exit /b 0
)

where winget >nul 2>&1
if errorlevel 1 exit /b 0

echo [Cloudflare] Instalando cloudflared gratis...
winget install --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 0

call :find_cloudflared
if defined CLOUDFLARED_EXE set "PUBLIC_TUNNEL_AVAILABLE=1"
exit /b 0

:find_cloudflared
set "CLOUDFLARED_EXE="
where cloudflared >nul 2>&1
if not errorlevel 1 (
    for /f "usebackq delims=" %%I in (`where cloudflared 2^>nul`) do (
        set "CLOUDFLARED_EXE=%%I"
        goto cloudflared_found
    )
)
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$m = Get-ChildItem -Path \"$env:LOCALAPPDATA\\Microsoft\\WinGet\\Packages\" -Recurse -Filter cloudflared.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName; if ($m) { Write-Output $m }"`) do (
        set "CLOUDFLARED_EXE=%%I"
        goto cloudflared_found
    )
)
if exist "%LOCALAPPDATA%\Programs\cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=%LOCALAPPDATA%\Programs\cloudflared\cloudflared.exe"
if not defined CLOUDFLARED_EXE if exist "%ProgramFiles%\Cloudflare\Cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=%ProgramFiles%\Cloudflare\Cloudflared\cloudflared.exe"
if not defined CLOUDFLARED_EXE if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Cloudflare\Cloudflared\cloudflared.exe" set "CLOUDFLARED_EXE=%ProgramFiles(x86)%\Cloudflare\Cloudflared\cloudflared.exe"

:cloudflared_found
if defined CLOUDFLARED_EXE set "CLOUDFLARED_EXE=%CLOUDFLARED_EXE%"
exit /b 0

:ensure_ollama
set "OLLAMA_EXE="
where ollama >nul 2>&1
if not errorlevel 1 set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_EXE if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles(x86)%\Ollama\ollama.exe"

if not defined OLLAMA_EXE (
    echo Ollama no encontrado.
    echo Instale Ollama y vuelva a iniciar el lanzador.
    echo URL esperada: %OLLAMA_BASE_URL%
    echo Modelo requerido: %OLLAMA_MODEL%
    pause
    exit /b 1
)

echo [Ollama] Verificando servicio local...
call :probe_ollama
if errorlevel 1 (
    echo [Ollama] Iniciando servicio...
    start "" /min cmd /c "\"%OLLAMA_EXE%\" serve"
    for /l %%I in (1,1,30) do (
        timeout /t 1 >nul
        call :probe_ollama
        if not errorlevel 1 goto ollama_ready
    )
    echo No se pudo iniciar el servicio Ollama en %OLLAMA_BASE_URL%.
    echo Cierre otras instancias de Ollama y pruebe de nuevo.
    pause
    exit /b 1
)

:ollama_ready
echo [Ollama] Servicio listo.
echo [Ollama] Verificando modelo %OLLAMA_MODEL%...
"%OLLAMA_EXE%" show "%OLLAMA_MODEL%" >nul 2>&1
if errorlevel 1 (
    echo [Ollama] Descargando modelo %OLLAMA_MODEL%... ^(la primera vez puede tardar^)
    "%OLLAMA_EXE%" pull "%OLLAMA_MODEL%"
    if errorlevel 1 (
        echo No se pudo descargar el modelo de Ollama.
        echo Modelo requerido: %OLLAMA_MODEL%
        echo Comando manual: ollama pull %OLLAMA_MODEL%
        pause
        exit /b 1
    )
)

"%OLLAMA_EXE%" show "%OLLAMA_MODEL%" >nul 2>&1
if errorlevel 1 (
    echo El servicio Ollama responde, pero el modelo %OLLAMA_MODEL% sigue sin estar disponible.
    echo Comando manual: ollama show %OLLAMA_MODEL%
    pause
    exit /b 1
)
exit /b 0
