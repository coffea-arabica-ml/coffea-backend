"""
Fixtures da suíte padrão: o modelo é um falso (monkeypatch de app.modelo.carregar) e o banco é
SQLite em memória (StaticPool). Os auxiliares ficam em tests/apoio.py.
"""
import pytest
from fastapi.testclient import TestClient

from apoio import ORIGEM, ORIGEM_NAO_PERMITIDA, ModeloFalso, config_de_teste
from app import modelo as modulo_modelo
from app.main import criar_app


@pytest.fixture
def modelo_falso():
    return ModeloFalso()


@pytest.fixture
def cliente(monkeypatch, tmp_path, modelo_falso):
    """Cliente com o modelo falso, banco em memória e o cabeçalho Origin em toda requisição."""
    yield from _cliente(monkeypatch, tmp_path, modelo_falso, ORIGEM)


@pytest.fixture
def cliente_de_fora(monkeypatch, tmp_path, modelo_falso):
    """O mesmo cliente, com uma origem que o CORS não libera."""
    yield from _cliente(monkeypatch, tmp_path, modelo_falso, ORIGEM_NAO_PERMITIDA)


def _cliente(monkeypatch, tmp_path, modelo, origem):
    monkeypatch.setattr(modulo_modelo, "carregar", lambda _config: modelo)
    with TestClient(criar_app(config_de_teste(tmp_path)), headers={"Origin": origem}) as c:
        yield c
