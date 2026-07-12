@echo off
setlocal
title Reparar microfono (Windows)
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo Este script necesita permisos de administrador.
  echo Cierra esta ventana, haz clic derecho en reparar_microfono.bat y elige:
  echo "Ejecutar como administrador".
  pause
  exit /b 1
)

echo [1/4] Reiniciando servicios de audio...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Try { Restart-Service AudioEndpointBuilder -Force -ErrorAction Stop; Restart-Service Audiosrv -Force -ErrorAction Stop; Write-Host 'Servicios OK' } Catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
  echo No se pudieron reiniciar servicios de audio.
  pause
  exit /b 1
)

echo [2/4] Re-inicializando dispositivo Intel Digital Microphones...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$mic = Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -like '*Intel*Digital Microphones*' } | Select-Object -First 1 -ExpandProperty PNPDeviceID; " ^
  "if (-not $mic) { Write-Host 'No se encontro dispositivo Intel Digital Microphones'; exit 1 }; " ^
  "Disable-PnpDevice -InstanceId $mic -Confirm:$false -ErrorAction Stop; Start-Sleep -Seconds 2; Enable-PnpDevice -InstanceId $mic -Confirm:$false -ErrorAction Stop; " ^
  "Write-Host ('Dispositivo reiniciado: ' + $mic)"
if errorlevel 1 (
  echo No se pudo reiniciar el dispositivo de microfono por script.
  echo Puedes hacerlo manualmente en Administrador de dispositivos.
)

echo [3/4] Abriendo configuracion de entrada y permisos de microfono...
start "" "ms-settings:sound"
start "" "ms-settings:privacy-microphone"
start "" "ms-settings:apps-volume"

echo [4/4] Listo.
echo 1) En Sonido, elige el microfono de entrada y verifica el medidor.
echo 2) En Privacidad, activa permisos de microfono.
echo 3) Cierra y abre Chrome/Edge por completo.
echo 4) Vuelve a ejecutar iniciar_chatbot.bat y prueba de nuevo.
pause
