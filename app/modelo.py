"""
O modelo do coffea-ml no backend: conferência dos pesos, carregamento e inferência.

Só este módulo mexe no sys.path (COFFEA_ML_DIR/model) e importa o inferencia, dentro de
carregar(), que o lifespan chama numa thread. O inferencia acrescenta ainda data/ e evaluation/ do
coffea-ml; nenhum módulo de lá se chama app (carregar() confere), então o pacote deste repositório
não é encoberto.

Os pesos ficam fora do git, nos caminhos do coffea-ml (model/pesos/MANIFESTO.md). Antes de
carregar, o tamanho e o SHA-256 de cada arquivo são comparados com a tabela do manifesto, lida a
cada subida: nenhum hash fica no código.
"""
import hashlib
import importlib
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Config

logger = logging.getLogger("coffea.modelo")

# Os caminhos padrão do inferencia (PASTA_CLASSIFICADOR e detector.PESOS_PADRAO), relativos ao
# coffea-ml. Ficam repetidos aqui porque a conferência dos pesos vem antes do import do inferencia
# (que traz o torch); tests/test_modelo_real.py confere que continuam iguais.
PASTA_CLASSIFICADOR_PADRAO = Path("model/runs/base_resnet50_bracol")
PESOS_DETECTOR_PADRAO = Path("model/runs/detector_base/weights/last.pt")
MANIFESTO = Path("model/pesos/MANIFESTO.md")
_LINHA_DO_MANIFESTO = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([\d.]+)\s*\|\s*`([0-9a-f]{64})`\s*\|")
_BLOCO = 1024 * 1024


class ErroDoModelo(Exception):
    """Falha prevista na conferência ou no carregamento. A mensagem vira o motivo do GET /: curta e
    sem caminhos do disco."""


@dataclass(frozen=True)
class EntradaDoManifesto:
    arquivo: str  # caminho relativo ao coffea-ml, como na tabela
    tamanho: int  # bytes
    sha256: str


@dataclass
class Modelo:
    """O modelo carregado, ou o motivo de não estar."""
    classificador: str
    detector: str
    carregado: bool = False
    pesos_verificados: bool = False
    motivo: str | None = None
    inferencia: object = field(default=None, repr=False)  # o módulo inferencia do coffea-ml
    modelos: object = field(default=None, repr=False)  # inferencia.Modelos

    def estado(self) -> dict:
        """O bloco "modelo" do GET /."""
        return {"carregado": self.carregado, "classificador": self.classificador,
                "detector": self.detector, "pesos_verificados": self.pesos_verificados,
                "motivo": self.motivo}

    def diagnosticar(self, conteudo: bytes) -> dict:
        """O diagnóstico do coffea-ml para os bytes do upload, como veio. Bloqueante: chame numa
        thread. Os modelos vão explícitos para valer os caminhos da configuração (sem eles, o
        inferencia carregaria os caminhos padrão)."""
        if not self.carregado:
            raise RuntimeError("o modelo não está carregado")
        return self.inferencia.diagnosticar_arquivo(conteudo, modelos=self.modelos)


def carregar(config: Config) -> Modelo:
    """Confere os pesos e carrega o modelo. Nunca lança: em qualquer falha, devolve o modelo
    indisponível, com o motivo, e o erro completo vai para o log. Bloqueante (SHA-256 e torch)."""
    pasta, pesos = caminhos_dos_pesos(config)
    modelo = Modelo(classificador=pasta.name, detector=nome_do_detector(pesos))
    if not config.carregar_modelo:
        modelo.motivo = "modelo desligado (COFFEA_CARREGAR_MODELO=0)"
        logger.warning("Subindo sem modelo: COFFEA_CARREGAR_MODELO=0. POST /diagnostico responde 503.")
        return modelo
    try:
        if not (config.coffea_ml_dir / "model" / "inferencia.py").is_file():
            raise ErroDoModelo("coffea-ml não encontrado (confira o COFFEA_ML_DIR)")
        if config.verificar_pesos:
            verificar_pesos([pasta / "melhor.pt", pesos], config.coffea_ml_dir)
            modelo.pesos_verificados = True
            logger.info("Pesos conferidos com o MANIFESTO.md (tamanho e SHA-256).")
        else:
            logger.warning("Conferência dos pesos desligada (COFFEA_VERIFICAR_PESOS=0).")
        inferencia = importar_inferencia(config.coffea_ml_dir)
        modelo.modelos = inferencia.carregar_modelos(pasta_do_classificador=pasta,
                                                     pesos_do_detector=pesos, dispositivo="cpu")
        modelo.inferencia = inferencia
        modelo.carregado = True
        logger.info("Modelo carregado: classificador %s, detector %s (CPU).",
                    modelo.classificador, modelo.detector)
    except ErroDoModelo as e:
        modelo.motivo = str(e)
        logger.error("Modelo indisponível: %s (coffea-ml em %s). POST /diagnostico responde 503.",
                     e, config.coffea_ml_dir)
    except Exception:
        modelo.motivo = "falha ao carregar o modelo (ver o log do servidor)"
        logger.exception("Falha ao carregar o modelo do coffea-ml. POST /diagnostico responde 503.")
    return modelo


def caminhos_dos_pesos(config: Config) -> tuple[Path, Path]:
    """(pasta do melhor.pt, arquivo do detector): os da configuração ou os padrão do inferencia."""
    pasta = config.pasta_classificador or config.coffea_ml_dir / PASTA_CLASSIFICADOR_PADRAO
    pesos = config.pesos_detector or config.coffea_ml_dir / PESOS_DETECTOR_PADRAO
    return pasta, pesos


def nome_do_detector(pesos: Path) -> str:
    """O nome do run (model/runs/<run>/weights/last.pt) ou o do arquivo, como o inferencia."""
    return pesos.parents[1].name if pesos.parent.name == "weights" else pesos.name


def importar_inferencia(coffea_ml_dir: Path):
    """O módulo inferencia do coffea-ml, com COFFEA_ML_DIR/model no sys.path."""
    pasta_do_modelo = str(coffea_ml_dir / "model")
    if pasta_do_modelo not in sys.path:
        sys.path.insert(0, pasta_do_modelo)
    inferencia = importlib.import_module("inferencia")
    if not Path(inferencia.__file__).resolve().is_relative_to(coffea_ml_dir.resolve()):
        raise ErroDoModelo("o módulo inferencia importado não é o do COFFEA_ML_DIR")
    conferir_nomes(coffea_ml_dir)
    return inferencia


def conferir_nomes(coffea_ml_dir: Path) -> None:
    """Nenhuma pasta do coffea-ml no sys.path pode ter um módulo app (encobriria este pacote)."""
    raiz = coffea_ml_dir.resolve()
    for entrada in sys.path:
        pasta = Path(entrada or ".").resolve()
        if pasta.is_relative_to(raiz) and ((pasta / "app.py").exists() or (pasta / "app").is_dir()):
            raise ErroDoModelo("conflito de nomes: o coffea-ml tem um módulo app")


# ------------------------------------------------------------------------------ pesos
def verificar_pesos(arquivos: list[Path], coffea_ml_dir: Path) -> None:
    """Tamanho e SHA-256 de cada arquivo contra a tabela do MANIFESTO.md. ErroDoModelo se algum
    faltar, não estiver no manifesto ou não conferir."""
    entradas = ler_manifesto(coffea_ml_dir / MANIFESTO)
    for arquivo in arquivos:
        if not arquivo.is_file():
            raise ErroDoModelo(f"pesos não encontrados: {arquivo.name}")
        esperado = entrada_do_manifesto(arquivo, entradas, coffea_ml_dir)
        if arquivo.stat().st_size != esperado.tamanho:
            raise ErroDoModelo(f"{arquivo.name} não confere com o MANIFESTO.md (tamanho)")
        if sha256_do_arquivo(arquivo) != esperado.sha256:
            raise ErroDoModelo(f"{arquivo.name} não confere com o MANIFESTO.md (SHA-256)")


def ler_manifesto(caminho: Path) -> list[EntradaDoManifesto]:
    """As linhas da tabela de pesos do MANIFESTO.md: arquivo, bytes (com ponto de milhar) e
    SHA-256. A lista "Arquivos que não são pesos da cadeia" não é tabela e fica de fora."""
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError as e:
        raise ErroDoModelo("MANIFESTO.md dos pesos não encontrado") from e
    entradas = [EntradaDoManifesto(m[1], int(m[2].replace(".", "")), m[3])
                for m in map(_LINHA_DO_MANIFESTO.match, texto.splitlines()) if m]
    if not entradas:
        raise ErroDoModelo("MANIFESTO.md sem a tabela de pesos")
    return entradas


def entrada_do_manifesto(arquivo: Path, entradas: list[EntradaDoManifesto],
                         coffea_ml_dir: Path) -> EntradaDoManifesto:
    """A linha do manifesto de um arquivo: pelo caminho relativo ao coffea-ml, se ele estiver lá;
    senão (caminho customizado), pelo nome do arquivo, que tem de ser único na tabela."""
    try:
        relativo = arquivo.resolve().relative_to(coffea_ml_dir.resolve()).as_posix()
    except ValueError:
        relativo = None
    for entrada in entradas:
        if entrada.arquivo == relativo:
            return entrada
    mesmo_nome = [e for e in entradas if Path(e.arquivo).name == arquivo.name]
    if len(mesmo_nome) != 1:
        raise ErroDoModelo(f"{arquivo.name} não está no MANIFESTO.md")
    return mesmo_nome[0]


def sha256_do_arquivo(caminho: Path) -> str:
    sha = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(_BLOCO), b""):
            sha.update(bloco)
    return sha.hexdigest()


# ------------------------------------------------------------------------------ JSON
def para_json(valor):
    """O valor com o que o json não serializa convertido sem mudar o valor: escalares e arrays do
    numpy (tolist) e tuplas viram tipos nativos. Os tipos nativos passam como estão."""
    if isinstance(valor, dict):
        return {chave: para_json(v) for chave, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [para_json(v) for v in valor]
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if hasattr(valor, "tolist"):  # numpy: o escalar vira o nativo, o array vira lista
        return para_json(valor.tolist())
    return valor
