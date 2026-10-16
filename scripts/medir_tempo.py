"""
Medição do RNF02 (diagnóstico em até 5 s), de ponta a ponta, com o servidor real. Fica fora da
suíte do pytest.

Sobe o servidor (python -m uvicorn app.main:app) numa porta própria, com o histórico num banco
temporário (o coffea.db não é tocado), e mede:
- a subida, até o GET / mostrar o modelo carregado;
- o POST /diagnostico de cada foto, do envio à resposta: a primeira chamada à parte e, das outras,
  a mediana, o p95 e o máximo.
Só tempo e código HTTP: o script não olha categorias, tipos de erro nem acertos.

Fotos: só de validação, ou as indicadas pelo gestor. Para o RNF02 (decisão de 16/10/2026): as 30
primeiras, em ordem alfabética, do BRACOT de treino. Nunca os conjuntos de teste fechados: o script
recusa caminhos de teste (a pasta test/ do BRACOT, teste_*, recortes de campo de teste) e arquivos
com o SHA-256 de um split "teste" dos manifestos do coffea-ml.

Uso (na raiz do repositório, com o venv ativo):
    python scripts/medir_tempo.py --pasta ../coffea-ml/data/raw/bracot/bracot-data/train --amostra 30
    python scripts/medir_tempo.py --pasta FOTOS --url http://127.0.0.1:8000   # servidor já no ar
"""
import argparse
import csv
import hashlib
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx

RAIZ_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_REPO))

from app.config import carregar_config  # noqa: E402

EXTENSOES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
LIMITE_RNF02 = 5.0  # segundos
MANIFESTOS = ("bracol.csv", "bracot.csv")  # em coffea-ml/data/manifests/


def main() -> int:
    argumentos = ler_argumentos()
    conferir_caminho(Path(argumentos.pasta))  # antes de listar a pasta
    fotos = escolher_fotos(Path(argumentos.pasta), argumentos.amostra)
    conferir_que_nao_sao_de_teste(fotos, carregar_config().coffea_ml_dir)
    print(f"{len(fotos)} fotos de {Path(argumentos.pasta).resolve()} "
          f"({fotos[0].name} a {fotos[-1].name})")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporaria:
        servidor, subida = None, None
        url = argumentos.url
        try:
            if url is None:
                url = f"http://127.0.0.1:{argumentos.porta}"
                servidor, subida = subir_servidor(url, argumentos.porta, Path(temporaria),
                                                  argumentos.tempo_de_subida)
            else:
                esperar_modelo(url, argumentos.tempo_de_subida)
            tempos, codigos = medir(url, fotos)
        finally:
            if servidor is not None:
                servidor.terminate()
                servidor.wait(timeout=30)
    relatar(subida, tempos, codigos)
    return 0


def ler_argumentos():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pasta", required=True, help="pasta com as fotos (JPG ou PNG)")
    parser.add_argument("--amostra", type=int, default=30,
                        help="as N primeiras fotos em ordem alfabética (padrão: 30)")
    parser.add_argument("--url", help="servidor já no ar (sem medir a subida)")
    parser.add_argument("--porta", type=int, default=8765, help="porta do servidor (padrão: 8765)")
    parser.add_argument("--tempo-de-subida", type=float, default=600,
                        help="espera máxima pela subida, em segundos (padrão: 600)")
    return parser.parse_args()


def escolher_fotos(pasta: Path, amostra: int) -> list[Path]:
    if not pasta.is_dir():
        sys.exit(f"pasta não encontrada: {pasta}")
    fotos = sorted((f for f in pasta.iterdir() if f.suffix.lower() in EXTENSOES),
                   key=lambda f: f.name)[:amostra]
    if len(fotos) < 2:
        sys.exit("são precisas pelo menos 2 fotos (a 1ª chamada fica à parte)")
    return fotos


def conferir_caminho(caminho: Path) -> None:
    """Sai com erro se o caminho passar por uma pasta de teste fechado."""
    partes = [p.lower() for p in caminho.resolve().parts]
    if any(p in ("test", "teste") or p.startswith("teste_") or "rotulagem_teste" in p
           for p in partes):
        sys.exit(f"recusado: {caminho} está numa pasta de teste fechado")


def conferir_que_nao_sao_de_teste(fotos: list[Path], coffea_ml_dir: Path) -> None:
    """Sai com erro se alguma foto for de um conjunto de teste fechado."""
    for foto in fotos:
        conferir_caminho(foto)
    proibidos = sha256_de_teste(coffea_ml_dir)
    if not proibidos:
        print("aviso: manifestos do coffea-ml não encontrados; só os caminhos foram conferidos")
    for foto in fotos:
        if hashlib.sha256(foto.read_bytes()).hexdigest() in proibidos:
            sys.exit(f"recusado: {foto} é uma foto de teste fechado (SHA-256 no manifesto)")


def sha256_de_teste(coffea_ml_dir: Path) -> set[str]:
    proibidos = set()
    for nome in MANIFESTOS:
        caminho = coffea_ml_dir / "data" / "manifests" / nome
        if caminho.is_file():
            with caminho.open(encoding="utf-8", newline="") as arquivo:
                proibidos |= {linha["sha256"] for linha in csv.DictReader(arquivo)
                              if linha.get("split") == "teste" and linha.get("sha256")}
    return proibidos


def subir_servidor(url: str, porta: int, temporaria: Path, espera: float):
    """O servidor real, com o histórico num banco temporário. Devolve (processo, segundos até o
    GET / mostrar o modelo carregado)."""
    ambiente = {**os.environ, "COFFEA_DB": str(temporaria / "medicao.db"),
                "COFFEA_CARREGAR_MODELO": "1"}
    log = temporaria / "servidor.log"
    inicio = time.perf_counter()
    with log.open("w", encoding="utf-8") as saida:
        servidor = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(porta)], cwd=RAIZ_REPO, env=ambiente, stdout=saida,
            stderr=subprocess.STDOUT)
    try:
        esperar_modelo(url, espera, servidor)
    except BaseException:
        servidor.terminate()
        servidor.wait(timeout=30)
        print(log.read_text(encoding="utf-8", errors="replace")[-3000:])
        raise
    return servidor, time.perf_counter() - inicio


def esperar_modelo(url: str, espera: float, servidor=None) -> None:
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        if servidor is not None and servidor.poll() is not None:
            sys.exit("o servidor terminou durante a subida (log abaixo)")
        try:
            modelo = httpx.get(f"{url}/", timeout=5).json()["modelo"]
        except (httpx.HTTPError, ValueError, KeyError):
            time.sleep(0.2)
            continue
        if modelo["carregado"]:
            return
        sys.exit(f"o servidor subiu sem o modelo: {modelo['motivo']}")
    sys.exit(f"o servidor não ficou pronto em {espera:.0f} s")


def medir(url: str, fotos: list[Path]) -> tuple[list[float], Counter]:
    """Segundos de cada POST (do envio à resposta lida) e a contagem dos códigos HTTP."""
    tempos, codigos = [], Counter()
    with httpx.Client(timeout=120) as cliente:
        for foto in fotos:
            conteudo = foto.read_bytes()  # a leitura do disco fica fora do tempo
            inicio = time.perf_counter()
            resposta = cliente.post(f"{url}/diagnostico", files={
                "imagem": (foto.name, conteudo, EXTENSOES[foto.suffix.lower()])})
            resposta.read()
            tempos.append(time.perf_counter() - inicio)
            codigos[resposta.status_code] += 1
    return tempos, codigos


def p95(valores: list[float]) -> float:
    """Percentil 95 pelo posto mais próximo (sem interpolação)."""
    ordenados = sorted(valores)
    return ordenados[math.ceil(0.95 * len(ordenados)) - 1]


def relatar(subida: float | None, tempos: list[float], codigos: Counter) -> None:
    primeira, demais = tempos[0], tempos[1:]
    acima = sum(t > LIMITE_RNF02 for t in tempos)
    print(f"\nMáquina: {platform.platform()}, {os.cpu_count()} CPUs lógicas, Python "
          f"{platform.python_version()}")
    print("\n| medida | segundos |\n|---|---:|")
    if subida is not None:
        print(f"| subida do servidor (até carregado=true) | {subida:.2f} |")
    print(f"| 1ª chamada | {primeira:.2f} |")
    print(f"| mediana das outras {len(demais)} | {statistics.median(demais):.2f} |")
    print(f"| p95 das outras {len(demais)} | {p95(demais):.2f} |")
    print(f"| máximo das outras {len(demais)} | {max(demais):.2f} |")
    print(f"\nCódigos HTTP: {dict(sorted(codigos.items()))}")
    print(f"Chamadas acima de {LIMITE_RNF02:.0f} s: {acima} de {len(tempos)}")


if __name__ == "__main__":
    sys.exit(main())
