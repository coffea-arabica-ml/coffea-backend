"""POST /diagnostico com o modelo falso: contrato, códigos HTTP, histórico e CORS."""
import logging

import pytest
from sqlalchemy.exc import SQLAlchemyError

from apoio import (ORIGEM, SUCESSO, ModeloFalso, contar, enviar, erro_do_modelo, fora_do_loop,
                   imagem)
from app.config import LIMITE_BYTES
from app.db import crud
from app.db.models import FolhaDiagnosticada

JPEG_MINIMO = b"\xff\xd8\xff"  # a assinatura; o modelo falso não decodifica


def folhas_gravadas(cliente) -> list[tuple]:
    with cliente.app.state.sessoes() as sessao:
        return [(f.folha_id, f.categoria, f.severidade, f.regiao_x, f.regiao_y, f.regiao_raio)
                for f in sessao.query(FolhaDiagnosticada).order_by(FolhaDiagnosticada.id)]


# ------------------------------------------------------------------------------ sucesso
def test_sucesso_devolve_o_dicionario_do_modelo_e_grava_por_folha(cliente, modelo_falso):
    resposta = enviar(cliente, imagem("JPEG"))
    assert resposta.status_code == 200
    assert resposta.json() == SUCESSO
    assert "imagemUrl" not in resposta.json()
    assert contar(cliente) == (1, 3)
    assert folhas_gravadas(cliente) == [
        ("folha-1", "ferrugem", "baixa", 0.412, 0.377, 0.142),
        ("folha-2", "ferrugem", "alta", 0.2, 0.6, 0.1),  # duas da mesma categoria
        ("folha-3", "saudavel", "saudavel", 0.731, 0.664, 0.118),
    ]


def test_png_e_aceito(cliente):
    assert enviar(cliente, imagem("PNG"), "folha.png", "image/png").status_code == 200


def test_folha_saudavel_e_gravada(cliente, modelo_falso):
    modelo_falso.resposta = {"status": "sucesso", "folhas": [
        {"id": "folha-1", "categoria": "saudavel", "severidade": "saudavel",
         "regiao": {"x": 0.5, "y": 0.5, "raio": 0.5}}]}
    assert enviar(cliente, imagem()).status_code == 200
    assert folhas_gravadas(cliente) == [("folha-1", "saudavel", "saudavel", 0.5, 0.5, 0.5)]


def test_folha_sem_regiao_grava_nulos(cliente, modelo_falso):
    modelo_falso.resposta = {"status": "sucesso", "folhas": [
        {"id": "folha-1", "categoria": "phoma", "severidade": "muito_baixa"}]}
    assert enviar(cliente, imagem()).status_code == 200
    assert folhas_gravadas(cliente) == [("folha-1", "phoma", "muito_baixa", None, None, None)]


def test_inferencia_e_gravacao_rodam_fora_do_loop(cliente, modelo_falso, monkeypatch):
    threads = []
    gravar = crud.gravar_diagnostico

    def gravar_registrando(sessao, resposta):
        threads.append(fora_do_loop())
        return gravar(sessao, resposta)

    monkeypatch.setattr(crud, "gravar_diagnostico", gravar_registrando)
    assert enviar(cliente, imagem()).status_code == 200
    assert modelo_falso.chamadas[0][1] is True
    assert threads == [True]


def test_le_a_imagem_inteira_ate_o_limite(cliente, modelo_falso):
    conteudo = JPEG_MINIMO + b"\0" * (LIMITE_BYTES - len(JPEG_MINIMO))  # exatamente 10 MB
    assert enviar(cliente, conteudo).status_code == 200
    assert modelo_falso.chamadas[0][0] == LIMITE_BYTES


# --------------------------------------------------------------------- erros do modelo
@pytest.mark.parametrize("tipo", ["baixa_confianca", "planta_nao_identificada",
                                  "formato_invalido", "arquivo_muito_grande"])
def test_erro_do_modelo_sai_com_200_e_nao_e_gravado(cliente, modelo_falso, tipo):
    modelo_falso.resposta = erro_do_modelo(tipo)
    resposta = enviar(cliente, imagem())
    assert resposta.status_code == 200
    assert resposta.json() == erro_do_modelo(tipo)
    assert contar(cliente) == (0, 0)


# ----------------------------------------------------------------- falhas do histórico
def test_falha_ao_gravar_o_historico_nao_derruba_o_diagnostico(cliente, monkeypatch, caplog):
    def falhar(_sessao, _resposta):
        raise SQLAlchemyError("disco cheio")

    monkeypatch.setattr(crud, "gravar_diagnostico", falhar)
    with caplog.at_level(logging.ERROR, logger="coffea"):
        resposta = enviar(cliente, imagem())
    assert resposta.status_code == 200
    assert resposta.json() == SUCESSO
    assert "Falha ao gravar o histórico" in caplog.text
    assert contar(cliente) == (0, 0)


def test_gravacao_e_atomica(cliente, modelo_falso, caplog):
    """Duas folhas com o mesmo id: a 2ª fere o UNIQUE e nada do diagnóstico fica gravado."""
    folha = {"id": "folha-1", "categoria": "ferrugem", "severidade": "baixa"}
    modelo_falso.resposta = {"status": "sucesso", "folhas": [folha, dict(folha)]}
    with caplog.at_level(logging.ERROR, logger="coffea"):
        resposta = enviar(cliente, imagem())
    assert resposta.status_code == 200
    assert resposta.json() == modelo_falso.resposta
    assert contar(cliente) == (0, 0)
    assert "IntegrityError" in caplog.text


# ---------------------------------------------------------------------- erros do upload
def test_acima_de_10_mb_da_413(cliente, modelo_falso):
    resposta = enviar(cliente, JPEG_MINIMO + b"\0" * (LIMITE_BYTES - len(JPEG_MINIMO) + 1))
    assert resposta.status_code == 413
    assert resposta.json()["tipo"] == "arquivo_muito_grande"
    assert modelo_falso.chamadas == []


@pytest.mark.parametrize("formato", ["GIF", "WEBP"])
def test_gif_e_webp_dao_415(cliente, modelo_falso, formato):
    resposta = enviar(cliente, imagem(formato), f"folha.{formato.lower()}", "image/jpeg")
    assert resposta.status_code == 415
    assert resposta.json()["status"] == "erro"
    assert resposta.json()["tipo"] == "formato_invalido"
    assert modelo_falso.chamadas == []


def test_texto_com_nome_de_jpg_da_415(cliente):
    assert enviar(cliente, b"isto nao e uma imagem", "folha.jpg").status_code == 415


def test_sem_o_campo_imagem_da_422(cliente):
    for resposta in (cliente.post("/diagnostico"),
                     cliente.post("/diagnostico", files={"foto": ("a.jpg", imagem(), "image/jpeg")}),
                     cliente.post("/diagnostico", data={"imagem": "texto"})):
        assert resposta.status_code == 422
        assert resposta.json() == {"status": "erro", "tipo": "formato_invalido",
                                   "mensagem": 'Envie a foto no campo "imagem", em JPG ou PNG.'}


def test_arquivo_vazio_da_422(cliente, modelo_falso):
    resposta = enviar(cliente, b"")
    assert resposta.status_code == 422
    assert resposta.json()["tipo"] == "formato_invalido"
    assert modelo_falso.chamadas == []


def test_modelo_indisponivel_da_503(cliente, modelo_falso):
    modelo_falso.carregado = False
    resposta = enviar(cliente, imagem())
    assert resposta.status_code == 503
    assert resposta.json()["tipo"] == "erro_desconhecido"
    assert modelo_falso.chamadas == []


def test_excecao_inesperada_da_500_sem_detalhes(cliente, modelo_falso, caplog):
    modelo_falso.erro = RuntimeError("detalhe interno do torch")
    with caplog.at_level(logging.ERROR, logger="coffea"):
        resposta = enviar(cliente, imagem(), "foto-do-produtor.jpg")
    assert resposta.status_code == 500
    assert resposta.json()["tipo"] == "erro_desconhecido"
    assert "torch" not in resposta.text
    assert "Traceback" in caplog.text and "detalhe interno do torch" in caplog.text
    assert "foto-do-produtor" not in caplog.text  # nem a imagem nem o nome dela no log
    assert contar(cliente) == (0, 0)


def test_valor_nao_serializavel_vira_500_sem_gravar(cliente, modelo_falso):
    modelo_falso.resposta = {"status": "sucesso", "folhas": [], "detalhes": {"x": float("nan")}}
    assert enviar(cliente, imagem()).status_code == 500
    assert contar(cliente) == (0, 0)


# --------------------------------------------------------------------------------- CORS
def _sucesso(cliente, _modelo):
    return enviar(cliente, imagem())


def _erro_do_modelo(cliente, modelo):
    modelo.resposta = erro_do_modelo("baixa_confianca")
    return enviar(cliente, imagem())


def _indisponivel(cliente, modelo):
    modelo.carregado = False
    return enviar(cliente, imagem())


def _inesperado(cliente, modelo):
    modelo.erro = RuntimeError("falha")
    return enviar(cliente, imagem())


CASOS_DE_CORS = {
    "200 sucesso": (_sucesso, 200),
    "200 erro do modelo": (_erro_do_modelo, 200),
    "413": (lambda c, _m: enviar(c, JPEG_MINIMO + b"\0" * LIMITE_BYTES), 413),
    "415": (lambda c, _m: enviar(c, imagem("GIF")), 415),
    "422 sem campo": (lambda c, _m: c.post("/diagnostico"), 422),
    "422 vazio": (lambda c, _m: enviar(c, b""), 422),
    "503": (_indisponivel, 503),
    "500": (_inesperado, 500),
    "404 rota": (lambda c, _m: c.get("/nao-existe"), 404),
    "404 diagnóstico": (lambda c, _m: c.get("/diagnosticos/999"), 404),
    "422 limit": (lambda c, _m: c.get("/diagnosticos", params={"limit": 0}), 422),
    "200 histórico": (lambda c, _m: c.get("/diagnosticos"), 200),
    "200 raiz": (lambda c, _m: c.get("/"), 200),
}


@pytest.mark.parametrize("caso", CASOS_DE_CORS)
def test_cors_em_todas_as_respostas(cliente, modelo_falso, caso):
    requisicao, status = CASOS_DE_CORS[caso]
    resposta = requisicao(cliente, modelo_falso)
    assert resposta.status_code == status
    assert resposta.headers.get("access-control-allow-origin") in ("*", ORIGEM)
    if status >= 400:
        corpo = resposta.json()
        assert corpo["status"] == "erro" and corpo["tipo"] and corpo["mensagem"]


def test_preflight_do_navegador(cliente):
    resposta = cliente.options("/diagnostico", headers={
        "Origin": ORIGEM, "Access-Control-Request-Method": "POST"})
    assert resposta.status_code == 200
    assert resposta.headers.get("access-control-allow-origin") in ("*", ORIGEM)


def test_modelo_falso_tem_a_interface_do_modelo():
    """O falso e o real expõem os mesmos membros usados pelas rotas."""
    from app.modelo import Modelo
    real = Modelo(classificador="c", detector="d")
    for membro in ("carregado", "estado", "diagnosticar"):
        assert hasattr(real, membro) and hasattr(ModeloFalso(), membro)
    assert set(real.estado()) == set(ModeloFalso().estado())
