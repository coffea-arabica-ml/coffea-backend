from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Arquivo único do banco, relativo ao diretório de onde o servidor é iniciado.
# Sempre rode a partir da raiz do coffea-backend.
DATABASE_URL = "sqlite:///./coffea.db"

# check_same_thread=False é necessário porque o SQLite por padrão só permite
# uso pela mesma thread que criou a conexão, e o FastAPI atende requisições
# em threads diferentes.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(Engine, "connect")
def _ativar_foreign_keys(dbapi_connection, connection_record):
    """
    O SQLite NÃO aplica chaves estrangeiras por padrão. Sem este PRAGMA,
    problemas_detectados poderia apontar para um diagnóstico inexistente e o
    ON DELETE CASCADE não funcionaria.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Dependency do FastAPI: abre uma sessão por requisição e garante
    que ela seja fechada no final, mesmo se der erro.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
