"""
Medição do RNF03 (inferência por folha detectada em até 2 s sem GPU; até 1 s com GPU), etapa por
etapa, sem o servidor. Fica fora da suíte do pytest.

Carrega o modelo uma vez, como o backend (app.modelo.carregar: pesos conferidos com o MANIFESTO.md,
em CPU), e mede com time.perf_counter, em cada foto, na configuração padrão da cadeia (a do
backend):
- a decodificação da foto (dados.decodificar_imagem);
- o detector (inferencia.detectar);
- o recorte das folhas que a cadeia classifica (inferencia.recortar; o inferencia.decidir, que as
  escolhe, fica fora do tempo);
- o classificador com todas as folhas da foto num lote só (inferencia.classificar);
- o classificador com a 1ª folha sozinha, num lote de 1: o pior caso por folha, sem dividir o custo
  do lote;
- a cadeia inteira (Modelo.diagnosticar, a mesma chamada do POST /diagnostico).
Por foto, calcula o classificador em lote ÷ nº de folhas e a cadeia inteira ÷ nº de folhas (limite
superior conservador). A 1ª foto fica à parte (aquecimento); das outras, a mediana, o p95 e o
máximo de cada medida e, por nº de folhas, os da cadeia inteira e do classificador em lote. Só
tempos e contagem de folhas: o script não olha categorias nem acertos.

Fotos: as regras e as travas do scripts/medir_tempo.py. Para o RNF03, as do RNF02: as 30 primeiras,
em ordem alfabética, do BRACOT de treino. Nunca os conjuntos de teste fechados.

Uso (na raiz do repositório, com o venv ativo):
    python scripts/medir_folha.py --pasta ../coffea-ml/data/raw/bracot/bracot-data/train --amostra 30
No servidor, num contêiner avulso da imagem de produção (deploy/DEPLOY.md, seção 3), na pasta
deploy/:
    docker compose run --rm --no-deps -v /opt/cafelens/fotos-treino:/fotos:ro api \
        python scripts/medir_folha.py --pasta /fotos --amostra 30
"""
import argparse
import os
import platform
import statistics
import sys
import time
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_REPO))

from app.config import carregar_config  # noqa: E402
from app.modelo import carregar  # noqa: E402
from medir_tempo import (conferir_caminho, conferir_que_nao_sao_de_teste,  # noqa: E402
                         escolher_fotos, p95)

LIMITE_RNF03 = 2.0  # segundos por folha, sem GPU
MEDIDAS = (  # (chave, rótulo), na ordem da tabela; tempos em segundos
    ("folhas", "folhas classificadas (nº)"),
    ("decodificacao", "decodificação da foto"),
    ("detector", "detector (por foto)"),
    ("recorte", "recorte das folhas"),
    ("lote", "classificador, todas as folhas num lote"),
    ("lote_por_folha", "classificador em lote ÷ folhas"),
    ("lote_de_1", "classificador, lote de 1 folha"),
    ("cadeia", "cadeia inteira (por foto)"),
    ("cadeia_por_folha", "cadeia inteira ÷ folhas"),
)
LEITURAS = ("lote_por_folha", "lote_de_1", "detector", "cadeia_por_folha")  # as do veredito
CRITERIO = """\
Critério do veredito (RNF03: até 2 s por folha, sem GPU):
- leitura principal: classificador em lote ÷ folhas e classificador com lote de 1 folha;
- leituras mais duras: detector por foto e cadeia inteira ÷ folhas;
- de cada uma, a mediana, o p95 e o máximo das outras fotos, sem escolher a mais favorável. As
  fotos de 1 folha vêm em destaque: nelas, a cadeia ÷ folhas é a cadeia inteira."""


def main() -> int:
    argumentos = ler_argumentos()
    conferir_caminho(Path(argumentos.pasta))  # antes de listar a pasta
    fotos = escolher_fotos(Path(argumentos.pasta), argumentos.amostra)
    config = carregar_config()
    conferir_que_nao_sao_de_teste(fotos, config.coffea_ml_dir)
    print(f"{len(fotos)} fotos de {Path(argumentos.pasta).resolve()} "
          f"({fotos[0].name} a {fotos[-1].name})")

    modelo = carregar(config)  # como na subida do backend: pesos conferidos, em CPU
    if not modelo.carregado:
        sys.exit(f"modelo indisponível: {modelo.motivo}")
    if modelo.modelos.dispositivo.type != "cpu":
        sys.exit(f"dispositivo {modelo.modelos.dispositivo}: o script mede o caso sem GPU (cpu)")
    relatar([medir(modelo, foto) for foto in fotos])
    return 0


def ler_argumentos():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pasta", required=True, help="pasta com as fotos (JPG ou PNG)")
    parser.add_argument("--amostra", type=int, default=30,
                        help="as N primeiras fotos em ordem alfabética (padrão: 30)")
    return parser.parse_args()


def medir(modelo, foto: Path) -> dict:
    """Segundos de cada etapa numa foto e o nº de folhas que vão ao classificador, na
    configuração padrão da cadeia (a do backend)."""
    inferencia, modelos = modelo.inferencia, modelo.modelos
    config = inferencia.Configuracao()  # a que o diagnosticar_arquivo usa sem config
    conteudo = foto.read_bytes()  # a leitura do disco fica fora do tempo
    medida = {"foto": foto.name}
    imagem = cronometrar(medida, "decodificacao", inferencia.dados.decodificar_imagem, conteudo)
    deteccoes = cronometrar(medida, "detector", inferencia.detectar, imagem, config, modelos)
    preparo = inferencia.decidir(deteccoes, imagem.shape[0], imagem.shape[1], config)
    medida["folhas"] = len(preparo["folhas"])
    if preparo["folhas"]:  # sem folha (planos "nenhuma" e "fragmentos"), não há classificador
        recortes = cronometrar(medida, "recorte", inferencia.recortar, imagem, preparo, config)
        cronometrar(medida, "lote", inferencia.classificar, recortes, modelos)
        cronometrar(medida, "lote_de_1", inferencia.classificar, recortes[:1], modelos)
    cronometrar(medida, "cadeia", modelo.diagnosticar, conteudo)  # a chamada do POST /diagnostico
    if medida["folhas"]:
        medida["lote_por_folha"] = medida["lote"] / medida["folhas"]
        medida["cadeia_por_folha"] = medida["cadeia"] / medida["folhas"]
    return medida


def cronometrar(medida: dict, chave: str, funcao, *argumentos):
    """Chama funcao(*argumentos), guarda os segundos em medida[chave] e devolve o resultado."""
    inicio = time.perf_counter()
    resultado = funcao(*argumentos)
    medida[chave] = time.perf_counter() - inicio
    return resultado


def relatar(medidas: list[dict]) -> None:
    import torch  # já importado pelo modelo; as threads são lidas depois das medições

    primeira, demais = medidas[0], medidas[1:]
    print(f"\nMáquina: {platform.platform()}, {os.cpu_count()} CPUs lógicas, Python "
          f"{platform.python_version()}")
    print(f"torch {torch.__version__} no dispositivo cpu, com {torch.get_num_threads()} threads "
          f"(CUDA disponível: {'sim' if torch.cuda.is_available() else 'não'}; não usada)")
    print("As threads do torch são as que o ultralytics fixa no 1º predict, min(8, CPUs lógicas - "
          "1): tempos de máquinas com threads diferentes não são comparáveis.")
    if Path("/.dockerenv").exists():
        print("Contêiner: o healthcheck da imagem roda dentro deste contêiner (um python curto a "
              "cada 5 s nos primeiros 180 s e a cada 30 s depois) e disputa a CPU com a medição.")

    print(f"\n{CRITERIO}")
    print("\n| medida | 1ª foto | mediana | p95 | máximo |\n|---|---:|---:|---:|---:|")
    for chave, rotulo in MEDIDAS:
        valores = [m[chave] for m in demais if chave in m]
        resumo = (statistics.median(valores), p95(valores), max(valores)) if valores else (None,) * 3
        celulas = " | ".join(formatar(chave, v) for v in (primeira.get(chave), *resumo))
        print(f"| {rotulo} | {celulas} |")
    print(f"\nMediana, p95 e máximo das outras {len(demais)} fotos; tempos em segundos.")

    print(f"\nPor nº de folhas, nas outras {len(demais)} fotos (a coluna fotos é a distribuição):")
    print("\n| folhas | fotos | cadeia inteira, mediana | cadeia inteira, máximo "
          "| classificador em lote, mediana | classificador em lote, máximo |"
          "\n|---:|---:|---:|---:|---:|---:|")
    for n in sorted({m["folhas"] for m in demais}):
        grupo = [m for m in demais if m["folhas"] == n]
        celulas = []
        for chave in ("cadeia", "lote"):
            valores = [m[chave] for m in grupo if chave in m]
            celulas += [formatar(chave, statistics.median(valores) if valores else None),
                        formatar(chave, max(valores, default=None))]
        print(f"| {n} | {len(grupo)} | {' | '.join(celulas)} |")
    sem_folha = sum(m["folhas"] == 0 for m in medidas)
    print(f"\nFotos sem folha classificada, nas {len(medidas)}: {sem_folha} (ficam fora do recorte, "
          "do classificador e das divisões)")

    uma_folha = [(i, m) for i, m in enumerate(medidas) if m["folhas"] == 1]
    print(f"\nFotos de 1 folha, nas {len(medidas)}: {len(uma_folha)}")
    if uma_folha:
        print("\n| foto | detector | classificador | cadeia inteira |\n|---|---:|---:|---:|")
        for i, m in uma_folha:
            nome = m["foto"] + (" (1ª, aquecimento)" if i == 0 else "")
            print(f"| {nome} | {m['detector']:.3f} | {m['lote']:.3f} | {m['cadeia']:.3f} |")

    rotulos = dict(MEDIDAS)
    acima = "; ".join(f"{rotulos[c]}: {sum(m.get(c, 0) > LIMITE_RNF03 for m in medidas)}"
                      for c in LEITURAS)
    print(f"\nFotos acima de {LIMITE_RNF03:.0f} s, nas {len(medidas)}: {acima}")


def formatar(chave: str, valor) -> str:
    if valor is None:
        return "n/d"
    return f"{valor:g}" if chave == "folhas" else f"{valor:.3f}"


if __name__ == "__main__":
    sys.exit(main())
