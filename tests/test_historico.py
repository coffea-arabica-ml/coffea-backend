"""Critério de aceite da Frente 7: toda chamada bem-sucedida a /diagnostico
grava um registro, e o histórico é consultável (RF05)."""

import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path para permitir importações do pacote 'app'
DIRETORIO_RAIZ = Path(__file__).resolve().parent.parent
if str(DIRETORIO_RAIZ) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_RAIZ))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app

IMAGEM = ("folha.jpg", b"\xff\xd8\xff\xe0fake-jpeg-bytes", "image/jpeg")


@pytest.fixture()
def client():
    # Banco em memória, isolado por teste: o coffea.db real nunca é alterado.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_chamada_bem_sucedida_grava_registro(client):
    resp = client.post("/diagnostico", files={"imagem": IMAGEM})
    assert resp.status_code == 200

    historico = client.get("/historico").json()
    assert len(historico) == 1
    assert historico[0]["categoria"] == resp.json()["categoria"]
    assert historico[0]["severidade"] == resp.json()["severidade"]


def test_cada_chamada_grava_um_registro_novo(client):
    for _ in range(3):
        assert client.post("/diagnostico", files={"imagem": IMAGEM}).status_code == 200

    ids = [item["id"] for item in client.get("/historico").json()]
    assert len(ids) == 3
    assert ids == sorted(ids, reverse=True)  # mais recente primeiro


def test_requisicao_sem_imagem_nao_grava(client):
    assert client.post("/diagnostico").status_code == 422
    assert client.get("/historico").json() == []


def test_criado_em_sai_em_utc_com_fuso(client):
    client.post("/diagnostico", files={"imagem": IMAGEM})
    criado_em = client.get("/historico").json()[0]["criado_em"]
    assert criado_em.endswith(("Z", "+00:00"))


# Permite executar os testes diretamente com 'python test_historico.py' ou pelo botão Run
if __name__ == "__main__":
    import sys

    # Executa a suíte de testes do pytest para este arquivo com saída detalhada (-v)
    sys.exit(pytest.main(["-v", __file__]))

