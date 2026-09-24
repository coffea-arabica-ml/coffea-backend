@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo =========================================================
echo  Executando Suite de Testes Automatizados (pytest)
echo =========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [AVISO] O ambiente .venv ainda nao foi criado.
    echo Executando configuracao automatica primeiro...
    call configurar_ambiente.bat
)

.venv\Scripts\pytest.exe tests/test_historico.py -v

echo.
echo =========================================================
echo  Testes finalizados. Pressione qualquer tecla para fechar.
echo =========================================================
pause > nul
