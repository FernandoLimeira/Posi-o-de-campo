@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   POSICAO DE CAMPO - SERVIDOR LOCAL
echo ============================================
echo.
echo Acesse: http://localhost:8000
echo Para encerrar, pressione Ctrl+C.
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 server.py --host 0.0.0.0 --port 8000
) else (
  python server.py --host 0.0.0.0 --port 8000
)

pause
