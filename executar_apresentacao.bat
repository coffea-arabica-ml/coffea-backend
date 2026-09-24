@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo =========================================================
echo  Iniciando Demonstracao do Coffea Backend
echo =========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [AVISO] O ambiente .venv ainda nao foi criado.
    echo Executando configuracao automatica primeiro...
    call configurar_ambiente.bat
)

.venv\Scripts\python.exe demo_apresentacao.py

echo.
echo =========================================================
echo  Fim da Apresentacao. Pressione qualquer tecla para fechar.
echo =========================================================
pause > nul
