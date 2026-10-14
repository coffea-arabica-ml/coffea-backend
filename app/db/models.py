"""
Modelos SQLAlchemy.

Schema mínimo proposto pela Frente 7, atendendo ao RF05 (histórico de
diagnósticos consultável posteriormente).
"""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from .database import Base


class Diagnostico(Base):
    """Um registro de diagnóstico realizado pela rota POST /diagnostico."""

    __tablename__ = "diagnosticos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    categoria = Column(String, nullable=False)
    severidade = Column(String, nullable=False)
    # Preenchido automaticamente pelo banco no momento da inserção.
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
