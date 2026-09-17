@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   POSICAO DE CAMPO - LIMPEZA DE LEGADOS
echo ============================================
echo.

del /q "register.html" 2>nul
del /q "js\register.js" 2>nul
del /q "app.js" 2>nul
del /q "style.css" 2>nul
del /q "css\relatorio.css" 2>nul
del /q "js\relatorio.js" 2>nul
del /q "js\template-export-data.js" 2>nul
del /q "assets\template-export.png" 2>nul
if exist "posicao-campo-v1-auditoria-correcoes" rmdir /s /q "posicao-campo-v1-auditoria-correcoes"

echo Limpeza concluida. Os arquivos atuais do sistema foram preservados.
echo.
pause
