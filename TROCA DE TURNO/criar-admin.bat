@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   POSICAO DE CAMPO - CRIAR ADMINISTRADOR
echo ============================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -m backend.create_admin
) else (
  python -m backend.create_admin
)

echo.
pause
