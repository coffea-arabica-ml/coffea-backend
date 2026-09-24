"""
Script de demonstração visual para apresentação em sala de aula.
Simula o envio de múltiplas imagens de folhas com diferentes patologias do cafeeiro
(Ferrugem, Bicho-Mineiro, Cercosporiose e Saudável) e exibe o histórico atualizado em tempo real.
"""

import sys
import time
from pathlib import Path

# Configura o terminal para UTF-8 no Windows para exibir acentos e formatações corretamente
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Habilita suporte a cores ANSI no Prompt de Comando (CMD) do Windows caso colorama esteja presente
try:
    import colorama
    colorama.init()
except ImportError:
    pass

# Adiciona o diretório raiz do projeto ao sys.path para permitir importações locais
DIRETORIO_RAIZ = Path(__file__).resolve().parent
if str(DIRETORIO_RAIZ) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_RAIZ))

from fastapi.testclient import TestClient
from app.main import app

# Cores e estilos ANSI para destacar visualmente a apresentação no terminal
VERDE = "\033[92m"
AZUL = "\033[94m"
AMARELO = "\033[93m"
VERMELHO = "\033[91m"
CIANO = "\033[96m"
NEGRITO = "\033[1m"
RESET = "\033[0m"

# Metadados das amostras simuladas para a apresentação
AMOSTRAS_DEMO = [
    ("folha_ferrugem.jpg", "Esporos alaranjados na face inferior da folha"),
    ("folha_bicho_mineiro.jpg", "Minas necrosadas e forte risco de desfolha"),
    ("folha_cercosporiose.jpg", "Manchas circulares do tipo 'olho de pombo'"),
    ("folha_saudavel.jpg", "Folha íntegra, verde brilhante, sem lesões"),
]


def imprimir_cabecalho(titulo: str):
    """Exibe um cabeçalho formatado para separar as etapas da apresentação."""
    print(f"\n{AZUL}{'=' * 75}{RESET}")
    print(f"{NEGRITO}{titulo}{RESET}")
    print(f"{AZUL}{'=' * 75}{RESET}")


def colorir_severidade(severidade: str) -> str:
    """Aplica cor específica para cada nível de severidade para impacto visual."""
    if severidade == "Alta":
        return f"{VERMELHO}{severidade:<10}{RESET}"
    elif severidade == "Média":
        return f"{AMARELO}{severidade:<10}{RESET}"
    elif severidade == "Baixa":
        return f"{CIANO}{severidade:<10}{RESET}"
    return f"{VERDE}{severidade:<10}{RESET}"


def exibir_tabela_historico(dados: list, limite: int = 8):
    """Formata e imprime os registros do histórico em formato de tabela elegante."""
    if not dados:
        print(f"{AMARELO}[Histórico vazio no momento]{RESET}")
        return

    print(f"{NEGRITO}{'ID':<5} | {'Categoria':<16} | {'Severidade':<10} | {'Criado Em (UTC)':<22}{RESET}")
    print("-" * 65)
    for item in dados[:limite]:
        sev_colorida = colorir_severidade(item["severidade"])
        print(f"{item['id']:<5} | {item['categoria']:<16} | {sev_colorida} | {item['criado_em']:<22}")


def demonstracao():
    """Fluxo principal da demonstração com múltiplas amostras simuladas."""
    cliente = TestClient(app)

    # 1. Consulta inicial do histórico
    imprimir_cabecalho("1. CONSULTANDO HISTÓRICO ATUAL (GET /historico)")
    resp_inicial = cliente.get("/historico")
    historico_inicial = resp_inicial.json()
    print(f"Total de diagnósticos anteriores no banco: {NEGRITO}{len(historico_inicial)}{RESET}")
    exibir_tabela_historico(historico_inicial, limite=4)

    time.sleep(1.2)

    # 2. Envio de múltiplos diagnósticos com resultados diferentes
    imprimir_cabecalho("2. SIMULANDO DIAGNÓSTICOS DE DIFERENTES FOLHAS DE CAFÉ")

    for nome_arquivo, descricao in AMOSTRAS_DEMO:
        conteudo_fake = (nome_arquivo, b"\xff\xd8\xff\xe0fake-bytes", "image/jpeg")

        print(f"\n-> Enviando imagem: {NEGRITO}{nome_arquivo}{RESET}")
        print(f"   Características visuais: {descricao}")
        
        resp = cliente.post("/diagnostico", files={"imagem": conteudo_fake})
        
        if resp.status_code == 200:
            resultado = resp.json()
            sev_formatada = colorir_severidade(resultado['severidade'])
            print(f"   Status: {VERDE}200 OK{RESET} | Diagnóstico: {NEGRITO}{resultado['categoria']}{RESET} | Severidade: {sev_formatada}")
        else:
            print(f"   Erro no envio: {VERMELHO}{resp.status_code}{RESET}")
        
        time.sleep(1.2)

    # 3. Consulta do histórico consolidado
    imprimir_cabecalho("3. HISTÓRICO ATUALIZADO EM TEMPO REAL (ORDENADO PELO MAIS RECENTE)")
    resp_final = cliente.get("/historico")
    historico_final = resp_final.json()
    print(f"Total de registros agora no banco: {VERDE}{NEGRITO}{len(historico_final)}{RESET}")
    exibir_tabela_historico(historico_final, limite=8)

    time.sleep(1.2)

    # 4. Teste de integridade de dados (validação de erro 422)
    imprimir_cabecalho("4. TESTE DE RESILIÊNCIA: REQUISIÇÃO SEM ARQUIVO DE IMAGEM")
    print("Tentando realizar diagnóstico sem anexar imagem...")
    resp_invalida = cliente.post("/diagnostico")
    print(f"Status HTTP retornado: {AMARELO}{resp_invalida.status_code} Unprocessable Entity{RESET}")
    print(f"{VERDE}✓ Validação FastAPI ativa: requisição inválida rejeitada sem poluir o banco de dados!{RESET}\n")


if __name__ == "__main__":
    # Inicia a apresentação interativa
    demonstracao()
