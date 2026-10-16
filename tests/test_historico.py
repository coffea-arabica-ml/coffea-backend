"""Histórico por folha: rotas GET, schema (FK, cascade, UNIQUE) e banco incompatível."""
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apoio import ORIGEM, SUCESSO, ModeloFalso, config_de_teste, enviar, imagem
from app import modelo as modulo_modelo
from app.db import crud
from app.db.database import BancoIncompativel
from app.db.models import Diagnostico, FolhaDiagnosticada
from app.main import criar_app


def gravar(cliente, folhas, criado_em=None) -> int:
    with cliente.app.state.sessoes() as sessao:
        diagnostico_id = crud.gravar_diagnostico(sessao, {"status": "sucesso", "folhas": folhas})
        if criado_em is not None:
            with sessao.begin():
                sessao.get(Diagnostico, diagnostico_id).criado_em = criado_em
    return diagnostico_id


FOLHA = {"id": "folha-1", "categoria": "ferrugem", "severidade": "baixa",
         "regiao": {"x": 0.4, "y": 0.3, "raio": 0.1}}


# ------------------------------------------------------------------------------ rotas
def test_lista_vazia(cliente):
    resposta = cliente.get("/diagnosticos")
    assert resposta.status_code == 200
    assert resposta.json() == []


def test_lista_mais_recentes_primeiro_com_desempate_por_id(cliente):
    base = datetime(2026, 10, 14, 15, 2, 11)
    antigo = gravar(cliente, [FOLHA], base)
    empate_1 = gravar(cliente, [FOLHA], base + timedelta(hours=1))
    empate_2 = gravar(cliente, [FOLHA], base + timedelta(hours=1))
    ids = [d["id"] for d in cliente.get("/diagnosticos").json()]
    assert ids == [empate_2, empate_1, antigo]
    assert [d["id"] for d in cliente.get("/diagnosticos", params={"limit": 2}).json()] == ids[:2]


def test_limit_padrao_e_100_e_maximo_500(cliente):
    with cliente.app.state.sessoes() as sessao, sessao.begin():
        sessao.add_all(Diagnostico() for _ in range(501))
    assert len(cliente.get("/diagnosticos").json()) == 100
    assert len(cliente.get("/diagnosticos", params={"limit": 500}).json()) == 500


@pytest.mark.parametrize("limit", [0, 501, -1, "abc"])
def test_limit_fora_da_faixa_da_422_no_contrato(cliente, limit):
    resposta = cliente.get("/diagnosticos", params={"limit": limit})
    assert resposta.status_code == 422
    assert resposta.json() == {"status": "erro", "tipo": "erro_desconhecido",
                               "mensagem": "Parâmetro inválido: limit."}
    assert resposta.headers.get("access-control-allow-origin") in ("*", ORIGEM)


def test_detalhe_no_formato_do_contrato(cliente):
    diagnostico_id = gravar(cliente, [FOLHA, {"id": "folha-2", "categoria": "saudavel",
                                              "severidade": "saudavel"}],
                            datetime(2026, 10, 14, 15, 2, 11, 345678))
    resposta = cliente.get(f"/diagnosticos/{diagnostico_id}")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": diagnostico_id, "criadoEm": "2026-10-14T15:02:11Z",
        "folhas": [
            {"id": "folha-1", "categoria": "ferrugem", "severidade": "baixa",
             "regiao": {"x": 0.4, "y": 0.3, "raio": 0.1}},
            {"id": "folha-2", "categoria": "saudavel", "severidade": "saudavel"},  # sem região
        ]}


def test_detalhe_inexistente_da_404_no_contrato(cliente):
    resposta = cliente.get("/diagnosticos/999")
    assert resposta.status_code == 404
    assert resposta.json() == {"status": "erro", "tipo": "erro_desconhecido",
                               "mensagem": "Diagnóstico não encontrado."}


def test_detalhe_com_id_nao_numerico_da_422(cliente):
    resposta = cliente.get("/diagnosticos/abc")
    assert resposta.status_code == 422
    assert resposta.json()["tipo"] == "erro_desconhecido"


def test_criado_em_sai_em_utc_com_z(cliente):
    antes = datetime.now(timezone.utc).replace(microsecond=0)
    enviar(cliente, imagem())
    criado_em = cliente.get("/diagnosticos").json()[0]["criadoEm"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", criado_em)
    momento = datetime.strptime(criado_em, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert antes <= momento <= datetime.now(timezone.utc)


def test_post_aparece_no_historico_por_folha(cliente):
    enviar(cliente, imagem())
    [diagnostico] = cliente.get("/diagnosticos").json()
    assert [(f["id"], f["categoria"], f["severidade"], f["regiao"]) for f in diagnostico["folhas"]] \
        == [(f["id"], f["categoria"], f["severidade"], f["regiao"]) for f in SUCESSO["folhas"]]


def test_falha_no_banco_da_500_com_cors(cliente, monkeypatch):
    def falhar(*_args):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(crud, "listar_diagnosticos", falhar)
    monkeypatch.setattr(crud, "obter_diagnostico", falhar)
    for resposta in (cliente.get("/diagnosticos"), cliente.get("/diagnosticos/1")):
        assert resposta.status_code == 500
        assert resposta.json()["tipo"] == "erro_desconhecido"
        assert resposta.headers.get("access-control-allow-origin") in ("*", ORIGEM)


# ----------------------------------------------------------------------------- schema
def test_chaves_estrangeiras_ligadas(cliente):
    with cliente.app.state.sessoes() as sessao:
        assert sessao.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_folha_sem_diagnostico_e_recusada(cliente):
    with cliente.app.state.sessoes() as sessao:
        with pytest.raises(IntegrityError):
            with sessao.begin():
                sessao.add(FolhaDiagnosticada(diagnostico_id=999, folha_id="folha-1",
                                              categoria="ferrugem", severidade="baixa"))


def test_apagar_o_diagnostico_apaga_as_folhas_no_banco(cliente):
    diagnostico_id = gravar(cliente, [FOLHA, {**FOLHA, "id": "folha-2"}])
    with cliente.app.state.sessoes() as sessao, sessao.begin():
        # DELETE direto no SQL: o cascade testado é o do banco (ON DELETE CASCADE), não o do ORM.
        sessao.execute(text("DELETE FROM diagnosticos WHERE id = :id"), {"id": diagnostico_id})
    with cliente.app.state.sessoes() as sessao:
        assert sessao.query(FolhaDiagnosticada).count() == 0


def test_unique_por_folha_e_nao_por_categoria(cliente):
    primeiro = gravar(cliente, [FOLHA, {**FOLHA, "id": "folha-2"}])  # mesma categoria: pode
    gravar(cliente, [FOLHA])  # o mesmo folha_id em outro diagnóstico: pode
    with cliente.app.state.sessoes() as sessao:
        with pytest.raises(IntegrityError):
            with sessao.begin():
                sessao.add(FolhaDiagnosticada(diagnostico_id=primeiro, folha_id="folha-1",
                                              categoria="phoma", severidade="alta"))


def test_crud_recusa_diagnostico_de_erro(cliente):
    with cliente.app.state.sessoes() as sessao:
        with pytest.raises(ValueError):
            crud.gravar_diagnostico(sessao, {"status": "erro", "tipo": "baixa_confianca"})


# ------------------------------------------------------------------- banco em arquivo
def subir(monkeypatch, tmp_path, caminho_db):
    monkeypatch.setattr(modulo_modelo, "carregar", lambda _config: ModeloFalso())
    return TestClient(criar_app(config_de_teste(tmp_path, caminho_db=caminho_db)))


def test_banco_em_arquivo_persiste_entre_subidas(monkeypatch, tmp_path):
    caminho = tmp_path / "coffea.db"
    with subir(monkeypatch, tmp_path, caminho) as cliente:
        enviar(cliente, imagem())
    with subir(monkeypatch, tmp_path, caminho) as cliente:
        [diagnostico] = cliente.get("/diagnosticos").json()
        assert len(diagnostico["folhas"]) == 3


def test_banco_incompativel_impede_a_subida(monkeypatch, tmp_path):
    caminho = tmp_path / "coffea.db"
    with closing(sqlite3.connect(caminho)) as conexao, conexao:
        conexao.execute("CREATE TABLE diagnosticos (id INTEGER PRIMARY KEY, categoria TEXT, "
                        "severidade TEXT, criado_em TEXT)")
    with pytest.raises(BancoIncompativel, match="apague o coffea.db e suba de novo"):
        with subir(monkeypatch, tmp_path, caminho):
            pass


def test_banco_sem_unique_por_folha_e_incompativel(monkeypatch, tmp_path):
    caminho = tmp_path / "coffea.db"
    with closing(sqlite3.connect(caminho)) as conexao, conexao:
        conexao.executescript("""
            CREATE TABLE diagnosticos (id INTEGER PRIMARY KEY, criado_em DATETIME NOT NULL);
            CREATE TABLE folhas_diagnosticadas (
                id INTEGER PRIMARY KEY,
                diagnostico_id INTEGER NOT NULL REFERENCES diagnosticos (id) ON DELETE CASCADE,
                folha_id VARCHAR NOT NULL, categoria VARCHAR NOT NULL, severidade VARCHAR NOT NULL,
                regiao_x FLOAT, regiao_y FLOAT, regiao_raio FLOAT,
                UNIQUE (diagnostico_id, categoria));
        """)
    with pytest.raises(BancoIncompativel, match="UNIQUE"):
        with subir(monkeypatch, tmp_path, caminho):
            pass
