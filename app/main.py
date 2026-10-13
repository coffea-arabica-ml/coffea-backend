from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db import crud, models  # models importado para o create_all enxergar as tabelas
from app.db.database import Base, engine, get_db
from app.db.schemas import Categoria, DiagnosticoOut, ProblemaIn, Severidade

# Cria coffea.db e as tabelas, se ainda não existirem.
Base.metadata.create_all(bind=engine)

app = FastAPI()


def executar_modelo(imagem: UploadFile) -> list[ProblemaIn]:
    """
    Substituir pela inferência real (Frente 9). Deve devolver TODOS os
    problemas encontrados na folha; lista vazia = saudável.
    """
    return [
        ProblemaIn(categoria=Categoria.FERRUGEM, severidade=Severidade.BAIXA),
        ProblemaIn(categoria=Categoria.BICHO_MINEIRO, severidade=Severidade.ALTA),
    ]


@app.post("/diagnostico", response_model=DiagnosticoOut)
def diagnostico(imagem: UploadFile = File(...), db: Session = Depends(get_db)):
    # Se o modelo lançar exceção, nada é gravado e o FastAPI devolve erro.
    problemas = executar_modelo(imagem)

    # Só chega aqui em caso de sucesso: grava e responde com o registro salvo.
    return crud.criar_diagnostico(
        db,
        problemas=[(p.categoria.value, p.severidade.value) for p in problemas],
    )


@app.get("/diagnosticos", response_model=list[DiagnosticoOut])
def historico(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.listar_diagnosticos(db, limit=limit)


@app.get("/diagnosticos/{diagnostico_id}", response_model=DiagnosticoOut)
def detalhe(diagnostico_id: int, db: Session = Depends(get_db)):
    registro = crud.obter_diagnostico(db, diagnostico_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="Diagnóstico não encontrado.")
    return registro
