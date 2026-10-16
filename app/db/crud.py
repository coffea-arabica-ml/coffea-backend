"""Acesso ao histórico, separado das rotas. Funções bloqueantes: as rotas as chamam em threads."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Diagnostico, FolhaDiagnosticada


def gravar_diagnostico(sessao: Session, resposta: dict) -> int:
    """Grava um diagnóstico de sucesso, uma linha por folha, numa transação só (tudo ou nada; numa
    falha, o rollback é automático). Devolve o id."""
    if resposta.get("status") != "sucesso":
        raise ValueError("só diagnósticos com status 'sucesso' entram no histórico")
    with sessao.begin():
        diagnostico = Diagnostico(folhas=[_folha(f) for f in resposta.get("folhas", [])])
        sessao.add(diagnostico)
        sessao.flush()
        return diagnostico.id


def _folha(folha: dict) -> FolhaDiagnosticada:
    regiao = folha.get("regiao") or {}
    return FolhaDiagnosticada(folha_id=folha["id"], categoria=folha["categoria"],
                              severidade=folha["severidade"], regiao_x=regiao.get("x"),
                              regiao_y=regiao.get("y"), regiao_raio=regiao.get("raio"))


def listar_diagnosticos(sessao: Session, limit: int) -> list[Diagnostico]:
    """Os mais recentes primeiro; no empate de criado_em, o maior id."""
    consulta = (select(Diagnostico).options(selectinload(Diagnostico.folhas))
                .order_by(Diagnostico.criado_em.desc(), Diagnostico.id.desc()).limit(limit))
    return list(sessao.scalars(consulta))


def obter_diagnostico(sessao: Session, diagnostico_id: int) -> Diagnostico | None:
    return sessao.get(Diagnostico, diagnostico_id, options=[selectinload(Diagnostico.folhas)])


def serializar(diagnostico: Diagnostico) -> dict:
    """{"id", "criadoEm" (UTC, com "Z"), "folhas"}; a região só aparece se estiver gravada."""
    return {"id": diagnostico.id,
            "criadoEm": diagnostico.criado_em.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "folhas": [_folha_serializada(f) for f in diagnostico.folhas]}


def _folha_serializada(folha: FolhaDiagnosticada) -> dict:
    serializada = {"id": folha.folha_id, "categoria": folha.categoria,
                   "severidade": folha.severidade}
    if None not in (folha.regiao_x, folha.regiao_y, folha.regiao_raio):
        serializada["regiao"] = {"x": folha.regiao_x, "y": folha.regiao_y,
                                 "raio": folha.regiao_raio}
    return serializada
