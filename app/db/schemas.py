"""Schemas Pydantic usados para serializar as respostas da API."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator


class DiagnosticoOut(BaseModel):
    """Formato de cada registro retornado por GET /historico."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    severidade: str
    criado_em: datetime

    @field_validator("criado_em")
    @classmethod
    def _assume_utc(cls, valor: datetime) -> datetime:
        # O SQLite grava CURRENT_TIMESTAMP em UTC, mas devolve o datetime sem
        # fuso. Sem isto o JSON sai sem "Z" e o JavaScript (web e mobile)
        # interpreta o horário como local — no Brasil, 3 horas de diferença.
        return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor
