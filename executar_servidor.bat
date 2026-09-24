@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo =========================================================
echo  Iniciando Servidor FastAPI (Coffea Backend)
echo =========================================================
echo.
echo Documentacao interativa Swagger disponivel em:
echo  - http://127.0.0.1:8000/docs
echo.
echo Pressione CTRL+C para encerrar o servidor.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [AVISO] O ambiente .venv ainda nao foi criado.
    echo Executando configuracao automatica primeiro...
    call configurar_ambiente.bat
)

start "" http://127.0.0.1:8000/docs
.venv\Scripts\uvicorn.exe app.main:app --reload
