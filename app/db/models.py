from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Diagnostico(Base):
    """Uma análise de UMA imagem de folha. Pode ter 0, 1 ou vários problemas."""

    __tablename__ = "diagnosticos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    criado_em = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # 0 problemas = folha saudável.
    problemas = relationship(
        "ProblemaDetectado",
        back_populates="diagnostico",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProblemaDetectado.id",
        lazy="selectin",
    )

    @property
    def saudavel(self) -> bool:
        return len(self.problemas) == 0


class ProblemaDetectado(Base):
    """Um estresse biótico (com sua severidade) encontrado em um diagnóstico."""

    __tablename__ = "problemas_detectados"
    __table_args__ = (
        # A mesma categoria não pode aparecer duas vezes na mesma folha.
        UniqueConstraint("diagnostico_id", "categoria", name="uq_diag_categoria"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    diagnostico_id = Column(
        Integer,
        ForeignKey("diagnosticos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    categoria = Column(String, nullable=False)   # ex.: "Ferrugem"
    severidade = Column(String, nullable=False)  # ex.: "Baixa", "Alta"

    diagnostico = relationship("Diagnostico", back_populates="problemas")
