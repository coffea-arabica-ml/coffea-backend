"""
Configuração do coffea-backend, lida das variáveis de ambiente.

O .env da raiz do repositório (fora do git; o modelo é o .env.example) é lido pelo python-dotenv
sem sobrescrever o que já estiver no ambiente. Caminhos relativos valem a partir da raiz do
repositório, não do diretório de execução, e saem sempre absolutos.
"""
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_REPO = Path(__file__).resolve().parents[1]
LIMITE_BYTES = 10 * 1024 * 1024  # tamanho máximo do upload (10 MB), o mesmo dos frontends
_VERDADEIRO = {"1", "true", "sim", "yes"}
_FALSO = {"0", "false", "nao", "não", "no"}


@dataclass(frozen=True)
class Config:
    coffea_ml_dir: Path  # o clone do coffea-ml (COFFEA_ML_DIR)
    pasta_classificador: Path | None = None  # pasta do melhor.pt; None: o caminho padrão do inferencia
    pesos_detector: Path | None = None  # o last.pt; None: o caminho padrão do inferencia
    verificar_pesos: bool = True  # tamanho e SHA-256 contra o MANIFESTO.md antes de carregar
    concorrencia: int = 1  # inferências ao mesmo tempo
    carregar_modelo: bool = True  # False: sobe sem modelo, e o POST /diagnostico responde 503
    caminho_db: Path | None = RAIZ_REPO / "coffea.db"  # None: banco em memória (testes)


def carregar_config(ambiente: Mapping[str, str] | None = None) -> Config:
    """A configuração do ambiente: por padrão, o .env da raiz e o os.environ. Valor inválido dá
    ValueError com o nome da variável (o servidor não sobe)."""
    if ambiente is None:
        load_dotenv(RAIZ_REPO / ".env", override=False)
        ambiente = os.environ

    def valor(nome: str) -> str | None:
        return ambiente.get(nome, "").strip() or None

    return Config(
        coffea_ml_dir=caminho_absoluto(valor("COFFEA_ML_DIR") or "../coffea-ml"),
        pasta_classificador=_caminho_opcional(valor("COFFEA_PASTA_CLASSIFICADOR")),
        pesos_detector=_caminho_opcional(valor("COFFEA_PESOS_DETECTOR")),
        verificar_pesos=_booleano("COFFEA_VERIFICAR_PESOS", valor("COFFEA_VERIFICAR_PESOS"), True),
        concorrencia=_inteiro_positivo("COFFEA_CONCORRENCIA", valor("COFFEA_CONCORRENCIA"), 1),
        carregar_modelo=_booleano("COFFEA_CARREGAR_MODELO", valor("COFFEA_CARREGAR_MODELO"), True),
        caminho_db=caminho_absoluto(valor("COFFEA_DB") or "coffea.db"),
    )


def caminho_absoluto(valor: str | Path) -> Path:
    """O caminho absoluto; relativo vale a partir da raiz do repositório."""
    caminho = Path(valor).expanduser()
    return (caminho if caminho.is_absolute() else RAIZ_REPO / caminho).resolve()


def _caminho_opcional(valor: str | None) -> Path | None:
    return None if valor is None else caminho_absoluto(valor)


def _booleano(nome: str, valor: str | None, padrao: bool) -> bool:
    if valor is None:
        return padrao
    if valor.lower() in _VERDADEIRO:
        return True
    if valor.lower() in _FALSO:
        return False
    raise ValueError(f"{nome} deve ser 0 ou 1 (veio {valor!r})")


def _inteiro_positivo(nome: str, valor: str | None, padrao: int) -> int:
    if valor is None:
        return padrao
    try:
        numero = int(valor)
    except ValueError:
        numero = 0
    if numero < 1:
        raise ValueError(f"{nome} deve ser um inteiro maior ou igual a 1 (veio {valor!r})")
    return numero
