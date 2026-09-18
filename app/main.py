from typing import List

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.database import Base, engine, get_db
from app.db.models import Diagnostico
from app.db.schemas import DiagnosticoOut

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


@app.get("/")
def raiz():
    return {"status": "ok", "mensagem": "coffea-backend no ar"}


@app.post("/diagnostico")
async def diagnosticar(imagem: UploadFile = File(...), db: Session = Depends(get_db)):
    # TODO (Frente 9): substituir isso pela inferência real do modelo treinado no coffea-ml.
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