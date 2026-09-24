# coffea-backend

API que expõe o modelo de classificação de estresses bióticos em folhas
de Coffea arabica, consumida pelo coffea-web e pelo coffea-mobile.

## Stack
Python 3.13 + FastAPI. Ver justificativa completa no Guia Técnico (Drive,
pasta 06 - Backend).

## Rodando localmente
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
fastapi dev app/main.py --host 0.0.0.0
```

Documentação interativa das rotas em http://127.0.0.1:8000/docs

O `--host 0.0.0.0` é necessário para o coffea-mobile alcançar o servidor
pela rede Wi-Fi local.

## Rotas
- `GET /` — healthcheck
- `POST /diagnostico` — recebe imagem, devolve categoria e severidade
  (resposta simulada até a Frente 9 integrar o modelo real) e grava o
  resultado no histórico
- `GET /historico` — lista os diagnósticos já realizados, mais recentes
  primeiro (RF05)

## Banco de dados
SQLite (`coffea.db`, criado automaticamente na raiz do repositório na
primeira execução), acessado via SQLAlchemy. Modelos e conexão ficam em
`app/db/`. Sem migração versionada (Alembic) neste estágio — ver
justificativa no documento-mestre da Frente 7.

## Testes
```bash
pip install -r requirements.txt
python -m pytest
```
Os testes usam um banco SQLite em memória e verificam que toda chamada
bem-sucedida a `POST /diagnostico` grava um registro consultável em
`GET /historico`. O `coffea.db` real não é alterado.

## Contribuindo
Uma branch por tarefa, commits no imperativo, PR obrigatório antes de
merge na `main`. Sempre rode `pip freeze > requirements.txt` antes de
commitar uma dependência nova.
