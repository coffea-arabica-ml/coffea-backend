"""
Tabelas do histórico (RF05). Um diagnóstico de sucesso vira uma linha em diagnosticos e uma linha
por folha em folhas_diagnosticadas, inclusive as saudáveis. A foto não é guardada, e os erros de
diagnóstico não entram.

A unicidade é por (diagnostico_id, folha_id), não por categoria: uma foto pode ter várias folhas
com a mesma doença. Mudou o schema? Atualize o README (seção "Histórico") no mesmo commit.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def agora_utc() -> datetime:
    """Agora em UTC, sem fuso: o SQLite não guarda fuso, e criado_em é sempre UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Diagnostico(Base):
    __tablename__ = "diagnosticos"

    id: Mapped[int] = mapped_column(primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)  # UTC
    folhas: Mapped[list["FolhaDiagnosticada"]] = relationship(
        back_populates="diagnostico", cascade="all, delete-orphan", passive_deletes=True,
        order_by="FolhaDiagnosticada.id")


class FolhaDiagnosticada(Base):
    __tablename__ = "folhas_diagnosticadas"
    __table_args__ = (UniqueConstraint("diagnostico_id", "folha_id",
                                       name="uq_folha_por_diagnostico"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostico_id: Mapped[int] = mapped_column(
        ForeignKey("diagnosticos.id", ondelete="CASCADE"), index=True)
    folha_id: Mapped[str] = mapped_column(String)  # o id do contrato, ex.: "folha-1"
    categoria: Mapped[str] = mapped_column(String)  # código do contrato, ex.: "ferrugem"
    severidade: Mapped[str] = mapped_column(String)  # código do contrato, ex.: "baixa"
    regiao_x: Mapped[float | None] = mapped_column(Float)
    regiao_y: Mapped[float | None] = mapped_column(Float)
    regiao_raio: Mapped[float | None] = mapped_column(Float)
    diagnostico: Mapped[Diagnostico] = relationship(back_populates="folhas")
