import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.db import crud, models
from app.db.database import Base, get_db
from app.db.schemas import Categoria, ProblemaIn, Severidade

IMG = {"imagem": ("folha.jpg", b"x", "image/jpeg")}


@pytest.fixture()
def session_factory():
    # Banco em memória, isolado por teste (nunca toca o coffea.db real).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client(session_factory):
    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = _get_db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _modelo_devolve(monkeypatch, problemas):
    monkeypatch.setattr(main, "executar_modelo", lambda imagem: problemas)


def test_folha_com_varios_problemas_grava_um_diagnostico(client, monkeypatch):
    _modelo_devolve(monkeypatch, [
        ProblemaIn(categoria=Categoria.FERRUGEM, severidade=Severidade.BAIXA),
        ProblemaIn(categoria=Categoria.PHOMA, severidade=Severidade.MUITO_ALTA),
        ProblemaIn(categoria=Categoria.BICHO_MINEIRO, severidade=Severidade.ALTA),
    ])
    r = client.post("/diagnostico", files=IMG)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["saudavel"] is False
    assert len(corpo["problemas"]) == 3

    hist = client.get("/diagnosticos").json()
    assert len(hist) == 1  # UM diagnóstico, três problemas
    assert {p["categoria"] for p in hist[0]["problemas"]} == {
        "Ferrugem", "Phoma", "Bicho-mineiro"
    }


def test_folha_saudavel_grava_diagnostico_sem_problemas(client, monkeypatch):
    _modelo_devolve(monkeypatch, [])
    r = client.post("/diagnostico", files=IMG)
    assert r.status_code == 200
    assert r.json()["saudavel"] is True
    assert r.json()["problemas"] == []
    assert len(client.get("/diagnosticos").json()) == 1


def test_falha_do_modelo_nao_grava_nada(client, monkeypatch):
    def quebra(imagem):
        raise RuntimeError("modelo falhou")

    monkeypatch.setattr(main, "executar_modelo", quebra)
    with pytest.raises(RuntimeError):
        client.post("/diagnostico", files=IMG)
    assert client.get("/diagnosticos").json() == []


def test_historico_mais_recente_primeiro_e_limit(client, monkeypatch):
    _modelo_devolve(monkeypatch, [])
    ids = [client.post("/diagnostico", files=IMG).json()["id"] for _ in range(3)]
    hist = client.get("/diagnosticos").json()
    assert [d["id"] for d in hist] == sorted(ids, reverse=True)
    assert len(client.get("/diagnosticos?limit=2").json()) == 2
    assert client.get("/diagnosticos?limit=0").status_code == 422
    assert client.get("/diagnosticos?limit=501").status_code == 422


def test_detalhe_e_404(client, monkeypatch):
    _modelo_devolve(monkeypatch, [])
    novo = client.post("/diagnostico", files=IMG).json()
    assert client.get(f"/diagnosticos/{novo['id']}").status_code == 200
    assert client.get("/diagnosticos/9999").status_code == 404


def test_crud_rejeita_categoria_repetida(session_factory):
    db = session_factory()
    with pytest.raises(ValueError):
        crud.criar_diagnostico(db, [("Ferrugem", "Baixa"), ("Ferrugem", "Alta")])
    assert db.query(models.Diagnostico).count() == 0  # nada ficou pela metade


def test_banco_rejeita_duplicata_mesmo_sem_passar_pelo_crud(session_factory):
    db = session_factory()
    d = crud.criar_diagnostico(db, [("Ferrugem", "Baixa")])
    db.add(models.ProblemaDetectado(
        diagnostico_id=d.id, categoria="Ferrugem", severidade="Alta"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_key_ativa_e_cascade(session_factory):
    db = session_factory()
    d = crud.criar_diagnostico(db, [("Ferrugem", "Baixa"), ("Phoma", "Alta")])
    # FK inválida precisa ser recusada (prova que o PRAGMA está ligado).
    db.add(models.ProblemaDetectado(
        diagnostico_id=99999, categoria="Phoma", severidade="Baixa"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # Apagar o diagnóstico apaga os problemas.
    db.delete(db.get(models.Diagnostico, d.id))
    db.commit()
    assert db.execute(text("SELECT COUNT(*) FROM problemas_detectados")).scalar() == 0


def test_categoria_ou_severidade_invalida_nao_passa_na_api():
    with pytest.raises(ValueError):
        ProblemaIn(categoria="Ferrugemm", severidade="Alta")
    with pytest.raises(ValueError):
        ProblemaIn(categoria="Ferrugem", severidade="Média")
