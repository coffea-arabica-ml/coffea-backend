"""Schemas Pydantic usados para serializar as respostas da API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DiagnosticoOut(BaseModel):
    """Formato de cada registro retornado por GET /historico."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    severidade: str
    criado_em: datetime
