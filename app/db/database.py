"""
Banco do histórico (RF05): SQLite via SQLAlchemy, sem Alembic.

- O PRAGMA foreign_keys é ligado em cada conexão dos engines criados aqui (event.listen no
  engine), sem listener global na classe Engine.
- iniciar_banco cria as tabelas que faltam e recusa um banco com tabelas incompatíveis com
  app/db/models.py: o servidor não sobe e a mensagem pede para apagar o coffea.db.
"""
from pathlib import Path

from sqlalchemy import URL, Engine, Table, UniqueConstraint, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class BancoIncompativel(RuntimeError):
    pass


def criar_engine(caminho: Path | None) -> Engine:
    """Engine do SQLite no arquivo (absoluto) ou, com None, em memória numa conexão só (testes).
    check_same_thread=False porque as sessões rodam nas threads do pool do FastAPI."""
    argumentos = {"connect_args": {"check_same_thread": False}}
    if caminho is None:
        engine = create_engine("sqlite://", poolclass=StaticPool, **argumentos)
    else:
        engine = create_engine(URL.create("sqlite", database=str(caminho)), **argumentos)
    event.listen(engine, "connect", _ligar_chaves_estrangeiras)
    return engine


def _ligar_chaves_estrangeiras(conexao, _registro) -> None:
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def criar_sessoes(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def iniciar_banco(engine: Engine) -> None:
    """Confere as tabelas existentes e cria as que faltam. Bloqueante."""
    from app.db import models  # noqa: F401  (registra as tabelas no Base.metadata)

    problemas = problemas_de_schema(engine)
    if problemas:
        raise BancoIncompativel(
            f"O banco {engine.url.database or '(memória)'} tem tabelas incompatíveis com este "
            f"backend ({'; '.join(problemas)}): apague o coffea.db e suba de novo.")
    Base.metadata.create_all(engine)


def problemas_de_schema(engine: Engine) -> list[str]:
    """As diferenças entre as tabelas do banco e as do Base.metadata (colunas, chaves estrangeiras
    com ON DELETE e restrições UNIQUE). Tabela que ainda não existe não é problema."""
    inspetor = inspect(engine)
    existentes = set(inspetor.get_table_names())
    problemas = []
    for tabela in Base.metadata.sorted_tables:
        if tabela.name in existentes:
            problemas += _diferencas(inspetor, tabela)
    return problemas


def _diferencas(inspetor, tabela: Table) -> list[str]:
    nome = tabela.name
    colunas = sorted(c["name"] for c in inspetor.get_columns(nome))
    if colunas != sorted(c.name for c in tabela.columns):
        return [f"{nome}: colunas {', '.join(colunas)}"]
    chaves = {(tuple(fk["constrained_columns"]), fk["referred_table"],
               (fk.get("options") or {}).get("ondelete", "").upper())
              for fk in inspetor.get_foreign_keys(nome)}
    esperadas = {(tuple(c.column_keys), next(iter(c.elements)).column.table.name,
                  (c.ondelete or "").upper())
                 for c in tabela.foreign_key_constraints}
    unicas = {tuple(u["column_names"]) for u in inspetor.get_unique_constraints(nome)}
    unicas_esperadas = {tuple(c.name for c in u.columns) for u in tabela.constraints
                        if isinstance(u, UniqueConstraint)}
    problemas = []
    if chaves != esperadas:
        problemas.append(f"{nome}: chaves estrangeiras diferentes")
    if unicas != unicas_esperadas:
        problemas.append(f"{nome}: restrições UNIQUE diferentes")
    return problemas
