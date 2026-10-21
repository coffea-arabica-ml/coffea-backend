"""
coffea-backend: a API do diagnóstico de folhas de Coffea arabica, consumida pelo coffea-web e pelo
coffea-mobile (contrato no README).

Rodar: fastapi dev app/main.py --host 0.0.0.0. Testes: python -m pytest.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from app import erros, modelo
from app.config import LIMITE_BYTES, Config, carregar_config
from app.db import crud, database
from app.db.schemas import DiagnosticoHistorico
from app.erros import Erro, erro_interno, resposta_de_erro

logger = logging.getLogger("coffea")

ASSINATURAS = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")  # magic bytes do JPEG e do PNG
_ERROS_DO_UPLOAD = {
    413: {"model": Erro, "description": "Arquivo acima de 10 MB (arquivo_muito_grande)."},
    415: {"model": Erro, "description": "Não é JPG nem PNG (formato_invalido)."},
    422: {"model": Erro, "description": 'Sem o campo "imagem" ou arquivo vazio (formato_invalido).'},
    500: {"model": Erro, "description": "Erro inesperado (erro_desconhecido)."},
    503: {"model": Erro, "description": "Modelo indisponível (erro_desconhecido)."},
}
_ERRO_404 = {404: {"model": Erro, "description": "Diagnóstico não encontrado (erro_desconhecido)."}}

# O /docs (OpenAPI) oferece o código-fonte: o detector do coffea-ml usa o ultralytics, AGPL-3.0, e
# quem usa o serviço pela rede tem de achar o código (README, "Licença e código-fonte").
_ORGANIZACAO = "https://github.com/coffea-arabica-ml"
DESCRICAO = (
    "Diagnóstico de folhas de *Coffea arabica* (Cafélens). Contrato no README do coffea-backend.\n\n"
    "**Código-fonte e licença.** O serviço é distribuído sob a AGPL-3.0, porque o detector usa o "
    f"ultralytics. Código do serviço: [coffea-backend]({_ORGANIZACAO}/coffea-backend) e "
    f"[coffea-ml]({_ORGANIZACAO}/coffea-ml). Clientes: [coffea-web]({_ORGANIZACAO}/coffea-web) e "
    f"[coffea-mobile]({_ORGANIZACAO}/coffea-mobile)."
)
LICENCA = {"name": "AGPL-3.0", "url": "https://www.gnu.org/licenses/agpl-3.0.html"}

rotas = APIRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Na subida, o banco e o modelo. Tabelas incompatíveis no banco impedem a subida; falha no
    modelo não (o POST responde 503). Os dois bloqueiam (SQLite, SHA-256, torch): rodam em threads."""
    config = app.state.config
    engine = database.criar_engine(config.caminho_db)
    try:
        await run_in_threadpool(database.iniciar_banco, engine)
        app.state.sessoes = database.criar_sessoes(engine)
        app.state.modelo = await run_in_threadpool(modelo.carregar, config)
        app.state.semaforo = asyncio.Semaphore(config.concorrencia)
        yield
    finally:
        engine.dispose()


@rotas.get("/")
async def raiz(request: Request):
    return {"status": "ok", "mensagem": "coffea-backend no ar",
            "modelo": request.app.state.modelo.estado()}


@rotas.post("/diagnostico", responses=_ERROS_DO_UPLOAD)
async def diagnosticar(request: Request, imagem: UploadFile = File(...)):
    """Diagnóstico de uma foto (JPG ou PNG, até 10 MB) no contrato dos frontends. O resultado da
    inferência sai com 200, seja sucesso ou erro tipado do modelo: a requisição funcionou, a foto
    é que não serve. Os diagnósticos de sucesso entram no histórico, uma linha por folha."""
    # Frente 9 (feito): a resposta simulada deu lugar à inferência real do coffea-ml (app/modelo.py).
    # Erros capturados aqui, e não no handler global, para o 500 sair com CORS (app/erros.py).
    try:
        conteudo = await imagem.read(LIMITE_BYTES + 1)  # no máximo o limite + 1 byte
        if not conteudo:
            return resposta_de_erro(422, "formato_invalido",
                                    "O arquivo enviado está vazio. Envie uma foto em JPG ou PNG.")
        if len(conteudo) > LIMITE_BYTES:
            return resposta_de_erro(413, "arquivo_muito_grande",
                                    "A imagem passa de 10 MB. Envie uma foto menor.")
        if not conteudo.startswith(ASSINATURAS):
            return resposta_de_erro(415, "formato_invalido",
                                    "Formato não aceito. Envie uma foto em JPG ou PNG.")
        servico = request.app.state.modelo
        if not servico.carregado:
            return resposta_de_erro(503, "erro_desconhecido", "O diagnóstico está indisponível "
                                    "no momento. Tente de novo mais tarde.")
        async with request.app.state.semaforo:
            resposta = await run_in_threadpool(servico.diagnosticar, conteudo)
        resposta = modelo.para_json(resposta)
        corpo = JSONResponse(resposta)  # serializa antes de gravar: o que não vira JSON dá 500
        if resposta.get("status") == "sucesso":
            await run_in_threadpool(gravar_no_historico, request.app.state.sessoes, resposta)
        return corpo
    except Exception:
        logger.exception("Erro inesperado em POST /diagnostico")  # sem a imagem nem o nome dela
        return erro_interno()


def gravar_no_historico(sessoes: sessionmaker[Session], resposta: dict) -> None:
    """Grava o diagnóstico no histórico. Numa falha, o crud já desfez a transação, e o erro só vai
    para o log: o histórico é secundário, e os frontends guardam o próprio."""
    try:
        with sessoes() as sessao:
            crud.gravar_diagnostico(sessao, resposta)
    except Exception:
        logger.exception("Falha ao gravar o histórico; o diagnóstico foi devolvido mesmo assim.")


@rotas.get("/diagnosticos", response_model=list[DiagnosticoHistorico],
           response_model_exclude_none=True, responses={500: {"model": Erro}})
def listar_diagnosticos(request: Request, limit: int = Query(100, ge=1, le=500)):
    """Histórico (RF05), dos mais recentes para os mais antigos."""
    try:
        with request.app.state.sessoes() as sessao:
            return [crud.serializar(d) for d in crud.listar_diagnosticos(sessao, limit)]
    except Exception:
        logger.exception("Erro inesperado em GET /diagnosticos")
        return erro_interno()


@rotas.get("/diagnosticos/{diagnostico_id}", response_model=DiagnosticoHistorico,
           response_model_exclude_none=True, responses={**_ERRO_404, 500: {"model": Erro}})
def obter_diagnostico(request: Request, diagnostico_id: int):
    try:
        with request.app.state.sessoes() as sessao:
            diagnostico = crud.obter_diagnostico(sessao, diagnostico_id)
            if diagnostico is None:
                return resposta_de_erro(404, "erro_desconhecido", "Diagnóstico não encontrado.")
            return crud.serializar(diagnostico)
    except Exception:
        logger.exception("Erro inesperado em GET /diagnosticos/{id}")
        return erro_interno()


def configurar_log() -> None:
    """Mostra o log INFO do backend (logger "coffea") no terminal; o uvicorn só configura os dele."""
    if not logger.handlers:
        saida = logging.StreamHandler()
        saida.setFormatter(logging.Formatter("%(levelname)s:  [%(name)s] %(message)s"))
        logger.addHandler(saida)
        logger.setLevel(logging.INFO)


def criar_app(config: Config | None = None) -> FastAPI:
    """O app. Sem config, a configuração vem do ambiente (e do .env), lida aqui e não na subida: o
    CORS precisa das origens antes. Valor inválido impede a criação, com o nome da variável."""
    configurar_log()
    config = config or carregar_config()
    app = FastAPI(title="Coffea Backend", description=DESCRICAO, license_info=LICENCA,
                  lifespan=lifespan)
    app.state.config = config

    # Frente 10 (feito): só as origens do navegador em COFFEA_CORS_ORIGENS (padrão: o Vite local do
    # coffea-web). O app mobile nativo não manda Origin e não depende do CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origens),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    erros.registrar_handlers(app)
    app.include_router(rotas)
    return app


app = criar_app()
