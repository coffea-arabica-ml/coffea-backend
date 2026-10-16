"""
Corpos de erro no contrato dos frontends: {"status": "erro", "tipo": ..., "mensagem": ...}.

Os frontends tratam 413 como arquivo_muito_grande e 415 como formato_invalido; nas outras
respostas não-OK, repassam o corpo se ele tiver "tipo". Por isso todo erro deste backend sai neste
formato, em português e sem detalhes internos.

CORS: os handlers de RequestValidationError e de HTTPException rodam dentro do CORSMiddleware. O
handler de Exception, não: o Starlette o chama no ServerErrorMiddleware, fora do CORS, e o 500 sairia
sem Access-Control-Allow-Origin ("falha de rede" no navegador). Por isso as rotas capturam as
próprias exceções e devolvem erro_interno(); o handler global fica só como último recurso.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("coffea.erros")

MENSAGEM_ERRO_INTERNO = "Erro inesperado no servidor. Tente de novo em instantes."
MENSAGEM_SEM_IMAGEM = 'Envie a foto no campo "imagem", em JPG ou PNG.'
_MENSAGENS_HTTP = {404: "Rota não encontrada.", 405: "Método não permitido nesta rota."}


class Erro(BaseModel):
    """O corpo de erro do contrato (para o Swagger)."""
    status: str = "erro"
    tipo: str
    mensagem: str


def resposta_de_erro(status_http: int, tipo: str, mensagem: str) -> JSONResponse:
    return JSONResponse({"status": "erro", "tipo": tipo, "mensagem": mensagem},
                        status_code=status_http)


def erro_interno() -> JSONResponse:
    return resposta_de_erro(500, "erro_desconhecido", MENSAGEM_ERRO_INTERNO)


def registrar_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validacao)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(Exception, _inesperado)


async def _validacao(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422. No corpo (o upload do POST /diagnostico), formato_invalido; nos parâmetros (limit, id),
    erro_desconhecido, que é o tipo do contrato que sobra."""
    erros = exc.errors()
    if any(tuple(e.get("loc", ()))[:1] == ("body",) for e in erros):
        return resposta_de_erro(422, "formato_invalido", MENSAGEM_SEM_IMAGEM)
    campos = sorted({str(e["loc"][-1]) for e in erros if e.get("loc")})
    return resposta_de_erro(422, "erro_desconhecido",
                            f"Parâmetro inválido: {', '.join(campos) or 'requisição'}.")


async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    resposta = resposta_de_erro(exc.status_code, "erro_desconhecido",
                                _MENSAGENS_HTTP.get(exc.status_code, "Requisição não atendida."))
    if exc.headers:  # o Allow do 405
        resposta.headers.update(exc.headers)
    return resposta


async def _inesperado(_request: Request, exc: Exception) -> JSONResponse:
    """Último recurso (fora do CORS; ver o docstring do módulo)."""
    logger.error("Erro inesperado fora das rotas", exc_info=exc)
    return erro_interno()
