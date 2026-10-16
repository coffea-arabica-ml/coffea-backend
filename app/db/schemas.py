"""Formato das respostas do histórico (GET /diagnosticos e GET /diagnosticos/{id})."""
from pydantic import BaseModel, Field


class Regiao(BaseModel):
    x: float
    y: float
    raio: float


class FolhaHistorico(BaseModel):
    id: str = Field(examples=["folha-1"])
    categoria: str = Field(examples=["ferrugem"])
    severidade: str = Field(examples=["baixa"])
    regiao: Regiao | None = None  # só aparece se estiver gravada


class DiagnosticoHistorico(BaseModel):
    id: int = Field(examples=[7])
    criadoEm: str = Field(examples=["2026-10-14T15:02:11Z"])  # UTC
    folhas: list[FolhaHistorico]
