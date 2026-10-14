import io
import logging
from typing import List

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from sqlalchemy.orm import Session

from app.db.database import Base, engine, get_db
from app.db.models import Diagnostico
from app.db.schemas import DiagnosticoOut

logger = logging.getLogger("coffea-backend")

app = FastAPI(title="Coffea Backend")

# Cria as tabelas no banco SQLite caso ainda não existam.
# Sem Alembic neste estágio (Frente 7): o schema ainda é simples o
# suficiente para recriar o banco durante o desenvolvimento.
Base.metadata.create_all(bind=engine)

# Libera o acesso do frontend web (Vite) e do app mobile (Expo) durante o desenvolvimento.
# TODO (Frente 10): restringir isso a domínios específicos quando formos pra produção.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImagemInvalidaError(Exception):
    """Levantada quando o arquivo enviado não é uma imagem válida (formato errado ou corrompida)."""

    def __init__(self, mensagem: str):
        self.mensagem = mensagem


def resposta_de_erro(status_code: int, codigo: str, mensagem: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"erro": {"codigo": codigo, "mensagem": mensagem}},
    )


@app.exception_handler(ImagemInvalidaError)
async def tratar_imagem_invalida(request: Request, exc: ImagemInvalidaError):
    return resposta_de_erro(400, "IMAGEM_INVALIDA", exc.mensagem)


@app.exception_handler(RequestValidationError)
async def tratar_erro_de_validacao(request: Request, exc: RequestValidationError):
    return resposta_de_erro(
        422,
        "CAMPO_INVALIDO",
        "O campo 'imagem' é obrigatório e precisa ser um arquivo de imagem.",
    )


@app.exception_handler(Exception)
async def tratar_erro_inesperado(request: Request, exc: Exception):
    # Loga o erro real (com stack trace) só no servidor — quem chama a API nunca vê isso.
    logger.exception("Erro inesperado ao processar %s", request.url.path)
    return resposta_de_erro(
        500,
        "ERRO_INTERNO",
        "Ocorreu um erro inesperado. Tente novamente mais tarde.",
    )


@app.get("/")
def raiz():
    return {"status": "ok", "mensagem": "coffea-backend no ar"}


@app.post("/diagnostico")
async def diagnosticar(imagem: UploadFile = File(...), db: Session = Depends(get_db)):
    conteudo = await imagem.read()

    try:
        Image.open(io.BytesIO(conteudo)).verify()
    except Exception:
        raise ImagemInvalidaError(
            "O arquivo enviado não é uma imagem válida ou está corrompido."
        )

    # TODO (Frente 9): substituir isso pela inferência real do modelo treinado no coffea-ml.
    # Atenção: como .verify() consome o objeto de imagem, ao integrar o modelo real
    # reabra a imagem a partir de `conteudo` (ex: Image.open(io.BytesIO(conteudo))) de novo.
    categoria = "Ferrugem"
    severidade = "Baixa"

    # Frente 7 / RF05: toda chamada bem-sucedida grava um registro no histórico.
    registro = Diagnostico(categoria=categoria, severidade=severidade)
    db.add(registro)
    db.commit()

    return {
        "categoria": categoria,
        "severidade": severidade,
    }


@app.get("/historico", response_model=List[DiagnosticoOut])
def historico(db: Session = Depends(get_db)):
    """Consulta o histórico de diagnósticos, mais recentes primeiro (RF05)."""
    return db.query(Diagnostico).order_by(Diagnostico.criado_em.desc()).all()
