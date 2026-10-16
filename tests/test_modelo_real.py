"""
Testes com o modelo real do coffea-ml (marcador modelo_real). São pulados quando os pesos não estão
na máquina. Fotos (decisão do gestor, 16/10/2026): as 3 primeiras, em ordem alfabética, do BRACOT de
TREINO, lidas do coffea-ml, sem cópia para este repositório. Nunca os conjuntos de teste fechados.
Só se compara a igualdade das respostas; categorias e acertos não são olhados.
"""
import io
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import modelo as modulo_modelo
from app.config import RAIZ_REPO, carregar_config
from app.main import criar_app

CONFIG = replace(carregar_config(), caminho_db=None, carregar_modelo=True)
PASTA, PESOS = modulo_modelo.caminhos_dos_pesos(CONFIG)
FOTOS_DE_TREINO = CONFIG.coffea_ml_dir / "data" / "raw" / "bracot" / "bracot-data" / "train"

pytestmark = [
    pytest.mark.modelo_real,
    pytest.mark.skipif(not ((PASTA / "melhor.pt").is_file() and PESOS.is_file()),
                       reason="pesos do coffea-ml não estão na máquina"),
]


def primeiras_fotos(quantas: int) -> list:
    if not FOTOS_DE_TREINO.is_dir():
        return [pytest.param(None, marks=pytest.mark.skip(reason="fotos do BRACOT de treino "
                                                                  "não estão na máquina"))]
    fotos = sorted(f for f in FOTOS_DE_TREINO.iterdir() if f.suffix.lower() == ".jpg")[:quantas]
    return [pytest.param(f, id=f.name) for f in fotos]


@pytest.fixture(scope="module")
def cliente_real():
    with TestClient(criar_app(CONFIG)) as cliente:
        yield cliente


@pytest.fixture(scope="module")
def modelo_real(cliente_real):
    modelo = cliente_real.app.state.modelo
    assert modelo.carregado, modelo.motivo
    return modelo


def test_modelo_carregado_e_conferido(cliente_real, modelo_real):
    estado = cliente_real.get("/").json()["modelo"]
    assert estado["carregado"] is True and estado["motivo"] is None
    assert estado["pesos_verificados"] is CONFIG.verificar_pesos


@pytest.mark.parametrize("foto", primeiras_fotos(3))
def test_resposta_do_post_e_identica_a_do_inferencia(cliente_real, modelo_real, foto):
    assert "test" not in foto.parts  # nunca a pasta de teste do BRACOT
    conteudo = foto.read_bytes()
    resposta = cliente_real.post("/diagnostico", files={"imagem": (foto.name, conteudo,
                                                                   "image/jpeg")})
    esperado = modelo_real.inferencia.diagnosticar_arquivo(conteudo, modelos=modelo_real.modelos)
    assert resposta.status_code == 200
    assert resposta.json() == esperado


@pytest.mark.parametrize("cor", [(128, 128, 128), (0, 0, 0)], ids=["cinza", "preta"])
def test_foto_sem_folha_da_erro_tipado_do_modelo(cliente_real, modelo_real, cor):
    buffer = io.BytesIO()
    Image.new("RGB", (1024, 768), cor).save(buffer, format="JPEG")
    antes = len(cliente_real.get("/diagnosticos").json())
    resposta = cliente_real.post("/diagnostico", files={"imagem": ("sem-folha.jpg",
                                                                   buffer.getvalue(), "image/jpeg")})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "erro"
    assert corpo["tipo"] in {"planta_nao_identificada", "baixa_confianca"}
    assert corpo["mensagem"]
    assert len(cliente_real.get("/diagnosticos").json()) == antes  # erro não entra no histórico


def test_sem_conflito_com_o_pacote_app(modelo_real):
    assert Path(sys.modules["app"].__file__).resolve().parent == RAIZ_REPO / "app"
    assert Path(modelo_real.inferencia.__file__).resolve().is_relative_to(
        CONFIG.coffea_ml_dir.resolve())


def test_caminhos_padrao_sao_os_do_inferencia(modelo_real):
    inferencia = modelo_real.inferencia
    assert (CONFIG.coffea_ml_dir / modulo_modelo.PASTA_CLASSIFICADOR_PADRAO).resolve() \
        == inferencia.PASTA_CLASSIFICADOR.resolve()
    assert (CONFIG.coffea_ml_dir / modulo_modelo.PESOS_DETECTOR_PADRAO).resolve() \
        == inferencia.detector.PESOS_PADRAO.resolve()
