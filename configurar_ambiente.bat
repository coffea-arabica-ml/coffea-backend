@echo off
chcp 65001 > nul
echo =========================================================
echo  Configurando o Ambiente do Coffea Backend na Faculdade
echo =========================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado no PATH do sistema.
    echo Por favor, certifique-se de que o Python 3.10+ esta instalado neste computador.
    pause
    exit /b 1
)

echo [1/3] Verificando ambiente virtual (.venv)...
if not exist ".venv" (
    echo Criando ambiente virtual .venv...
    python -m venv .venv
) else (
    echo Ambiente .venv ja existe.
)

echo.
echo [2/3] Atualizando pip...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet

echo.
echo [3/3] Instalando dependencias do requirements.txt...
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

echo.
echo =========================================================
echo  Configuracao concluida com sucesso!
echo  Agora voce pode rodar 'executar_apresentacao.bat' ou 'executar_testes.bat'.
echo =========================================================
echo.
pause
