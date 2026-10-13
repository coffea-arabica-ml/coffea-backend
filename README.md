# Camada de banco de dados — Frente 7

SGBD: **SQLite**, via **SQLAlchemy** (decisão registrada no Documento-mestre da Frente 7).

## 1. Estrutura

```
coffea-backend/
├── requirements.txt          # sqlalchemy, fastapi, python-multipart
├── requirements-dev.txt      # pytest, httpx
├── app/
│   ├── main.py
│   └── db/
│       ├── __init__.py
│       ├── database.py       # engine, sessão, get_db, PRAGMA foreign_keys
│       ├── models.py         # tabelas
│       ├── schemas.py        # validação/serialização (Pydantic)
│       └── crud.py           # gravação e consulta
└── tests/test_diagnosticos.py
```

## 2. Modelo de dados: uma folha pode ter vários problemas

Um **diagnóstico** = uma análise de uma imagem. Cada problema encontrado é uma linha em
`problemas_detectados`. **Folha saudável = diagnóstico com zero problemas** (campo `saudavel` na API).

```
diagnosticos 1 ───< N problemas_detectados
```

### Tabela `diagnosticos`

| Campo | Tipo | Descrição |
|---|---|---|
| id | Integer (PK, autoincrement) | Identificador do diagnóstico |
| criado_em | DateTime | Data/hora, preenchida automaticamente (UTC) |

### Tabela `problemas_detectados`

| Campo | Tipo | Descrição |
|---|---|---|
| id | Integer (PK, autoincrement) | Identificador do problema |
| diagnostico_id | Integer (FK → diagnosticos.id, `ON DELETE CASCADE`, indexado) | Diagnóstico ao qual pertence |
| categoria | String | Ferrugem, Bicho-mineiro, Phoma ou Cercosporiose |
| severidade | String | Muito baixa, Baixa, Alta ou Muito alta |

Restrição: `UNIQUE (diagnostico_id, categoria)` — a mesma categoria não aparece duas vezes na mesma folha.

Notas:
- Os valores válidos de categoria/severidade são impostos pelos enums em `schemas.py` (o banco guarda texto).
- `criado_em` é gravado em UTC, mas o SQLite não guarda fuso: a API devolve sem `Z`. O frontend deve tratar como UTC.
- O `PRAGMA foreign_keys=ON` (em `database.py`) é obrigatório: sem ele o SQLite ignora a FK e o cascade.

## 3. API

| Rota | Descrição |
|---|---|
| `POST /diagnostico` | Recebe `imagem`, roda o modelo, **grava o diagnóstico com todos os problemas** e devolve o registro salvo. Se o modelo falhar, nada é gravado. |
| `GET /diagnosticos?limit=100` | Histórico (RF05), mais recentes primeiro. `limit` entre 1 e 500. |
| `GET /diagnosticos/{id}` | Um diagnóstico (404 se não existir). |

Exemplo de resposta:

```json
{
  "id": 7,
  "criado_em": "2026-10-13T14:02:11.123456",
  "problemas": [
    {"categoria": "Ferrugem", "severidade": "Baixa"},
    {"categoria": "Bicho-mineiro", "severidade": "Alta"}
  ],
  "saudavel": false
}
```

**Mudança de contrato:** antes a resposta era `{"categoria": ..., "severidade": ...}`. Agora é a lista `problemas`.
Frentes 5 (Frontend) e 9 (Modelagem) precisam ser avisadas: a inferência deve devolver uma lista de
problemas (`executar_modelo` em `main.py`), não um par único.

## 4. Rodar

```bash
cd coffea-backend            # sempre da raiz: coffea.db é criado relativo a este diretório
source venv/bin/activate
pip install -r requirements.txt
fastapi dev app/main.py --host 0.0.0.0
```

Teste manual: `POST /diagnostico` em `/docs`, confira se `coffea.db` aparece e se `GET /diagnosticos` lista o registro.

## 5. Testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

Os testes usam banco em memória e não tocam o `coffea.db` real.

## 6. Mudou o schema? (regra do projeto)

1. Altere `models.py`.
2. Atualize as tabelas da seção 2 **no mesmo commit**.
3. Sem Alembic neste estágio: **apague o `coffea.db`** e deixe o `create_all` recriar.
   (Se você já tinha um `coffea.db` com a tabela antiga, ele precisa ser apagado agora.)
4. Troca futura de SGBD: altere `DATABASE_URL` em `database.py`.
