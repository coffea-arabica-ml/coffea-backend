from typing import Sequence

from sqlalchemy.orm import Session

from . import models


def criar_diagnostico(
    db: Session, problemas: Sequence[tuple[str, str]]
) -> models.Diagnostico:
    """
    Grava UM diagnóstico com todos os seus problemas, em uma única transação
    (ou grava tudo, ou não grava nada).

    `problemas` é uma lista de (categoria, severidade). Lista vazia = folha
    saudável. Categorias repetidas são rejeitadas com ValueError.
    """
    categorias = [c for c, _ in problemas]
    if len(categorias) != len(set(categorias)):
        raise ValueError("Categoria repetida no mesmo diagnóstico.")

    registro = models.Diagnostico(
        problemas=[
            models.ProblemaDetectado(categoria=c, severidade=s)
            for c, s in problemas
        ]
    )
    try:
        db.add(registro)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(registro)
    return registro


def listar_diagnosticos(db: Session, limit: int = 100) -> list[models.Diagnostico]:
    """Histórico (RF05), mais recentes primeiro, com desempate estável por id."""
    return (
        db.query(models.Diagnostico)
        .order_by(models.Diagnostico.criado_em.desc(), models.Diagnostico.id.desc())
        .limit(limit)
        .all()
    )


def obter_diagnostico(db: Session, diagnostico_id: int) -> models.Diagnostico | None:
    return db.get(models.Diagnostico, diagnostico_id)
