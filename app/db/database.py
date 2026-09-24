"""
Conexão com o banco de dados (Frente 7 — Banco de Dados).

Banco escolhido: SQLite, acessado via SQLAlchemy.
Motivo: volume de dados baixo (projeto de demonstração acadêmica) e prazo
apertado — um arquivo único, sem servidor separado para configurar, é
suficiente e evita mais uma peça de infraestrutura.

Se o projeto precisar trocar de SGBD no futuro (ex.: PostgreSQL), basta
trocar a string de conexão abaixo — o SQLAlchemy abstrai o resto.

Sem migração versionada (Alembic) neste estágio: o schema ainda é pequeno
o suficiente para recriar o banco durante o desenvolvimento.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Localiza o arquivo coffea.db de forma absoluta na raiz do repositório,
# garantindo que funcione mesmo se o comando for executado de outro diretório.
DIRETORIO_RAIZ = Path(__file__).resolve().parent.parent.parent
DB_PATH = DIRETORIO_RAIZ / "coffea.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# check_same_thread=False é necessário só para SQLite: o FastAPI pode
# atender requisições em threads diferentes da que criou a conexão.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Dependency do FastAPI: abre uma sessão por requisição e garante que
    ela seja fechada no final, mesmo se a rota levantar uma exceção.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
