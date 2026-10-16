"""
Apoio da suíte padrão, que roda sem os pesos: o modelo falso, as respostas de exemplo, as imagens
(geradas com o Pillow, sem arquivos binários no git) e a configuração com o banco em memória.
"""
import asyncio
import copy
import io

from PIL import Image

from app.config import Config
from app.db.models import Diagnostico, FolhaDiagnosticada

ORIGEM = "http://localhost:5173"  # o Vite do coffea-web

# Três folhas, duas da mesma categoria, com os extras do modelo (o backend repassa como veio).
SUCESSO = {
    "status": "sucesso",
    "folhas": [
        {"id": "folha-1", "categoria": "ferrugem", "severidade": "baixa",
         "regiao": {"x": 0.412, "y": 0.377, "raio": 0.142}, "confianca": 0.81,
         "scoreDeteccao": 0.93, "caixa": [0.28, 0.21, 0.55, 0.52], "cortadaNaBorda": False},
        {"id": "folha-2", "categoria": "ferrugem", "severidade": "alta",
         "regiao": {"x": 0.2, "y": 0.6, "raio": 0.1}, "confianca": 0.7,
         "scoreDeteccao": 0.9, "caixa": [0.1, 0.5, 0.3, 0.7], "cortadaNaBorda": False},
        {"id": "folha-3", "categoria": "saudavel", "severidade": "saudavel",
         "regiao": {"x": 0.731, "y": 0.664, "raio": 0.118}, "confianca": 0.21,
         "scoreDeteccao": 0.88, "caixa": [0.63, 0.52, 0.86, 0.81], "cortadaNaBorda": True},
    ],
    "detalhes": {"plano": "deteccao", "regra": None, "deteccoes": 3, "recorte": "B",
                 "decisao": "duas_etapas", "classificador": "base_resnet50_bracol",
                 "detector": "detector_base"},
}


def erro_do_modelo(tipo: str) -> dict:
    return {"status": "erro", "tipo": tipo, "mensagem": f"mensagem de {tipo}",
            "detalhes": {"plano": "nenhuma", "regra": 3}}


def imagem(formato: str = "JPEG", tamanho=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, (40, 120, 40)).save(buffer, format=formato)
    return buffer.getvalue()


class ModeloFalso:
    """Mesma interface do app.modelo.Modelo. Registra se cada chamada rodou fora do loop."""

    def __init__(self, resposta: dict | None = None, erro: Exception | None = None,
                 carregado: bool = True):
        self.resposta = SUCESSO if resposta is None else resposta
        self.erro = erro
        self.carregado = carregado
        self.chamadas = []  # (tamanho dos bytes, rodou fora do loop de eventos)

    def estado(self) -> dict:
        return {"carregado": self.carregado, "classificador": "base_resnet50_bracol",
                "detector": "detector_base", "pesos_verificados": self.carregado,
                "motivo": None if self.carregado else "modelo desligado (teste)"}

    def diagnosticar(self, conteudo: bytes) -> dict:
        self.chamadas.append((len(conteudo), fora_do_loop()))
        if self.erro is not None:
            raise self.erro
        return copy.deepcopy(self.resposta)


def fora_do_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return True
    return False


def config_de_teste(tmp_path, **mudancas) -> Config:
    """Banco em memória e um coffea-ml inexistente (o modelo vem do falso)."""
    padrao = {"coffea_ml_dir": tmp_path / "coffea-ml-inexistente", "caminho_db": None}
    return Config(**{**padrao, **mudancas})


def enviar(cliente, conteudo: bytes, nome: str = "folha.jpg", tipo: str = "image/jpeg"):
    return cliente.post("/diagnostico", files={"imagem": (nome, conteudo, tipo)})


def contar(cliente) -> tuple[int, int]:
    """(diagnósticos, folhas) gravados."""
    with cliente.app.state.sessoes() as sessao:
        return sessao.query(Diagnostico).count(), sessao.query(FolhaDiagnosticada).count()
