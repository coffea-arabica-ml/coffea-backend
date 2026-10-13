from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, computed_field


class Categoria(str, Enum):
    """Estresses bióticos (RF01). 'Saudável' = nenhum problema na lista."""
    FERRUGEM = "Ferrugem"
    BICHO_MINEIRO = "Bicho-mineiro"
    PHOMA = "Phoma"
    CERCOSPORIOSE = "Cercosporiose"


class Severidade(str, Enum):
    """Escala ordinal de severidade (RF02)."""
    MUITO_BAIXA = "Muito baixa"
    BAIXA = "Baixa"
    ALTA = "Alta"
    MUITO_ALTA = "Muito alta"


class ProblemaIn(BaseModel):
    categoria: Categoria
    severidade: Severidade


class ProblemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    categoria: str
    severidade: str


class DiagnosticoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criado_em: datetime
    problemas: list[ProblemaOut]

    @computed_field
    @property
    def saudavel(self) -> bool:
        return len(self.problemas) == 0
