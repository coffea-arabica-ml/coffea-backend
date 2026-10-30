# coffea-backend (Cafélens, Frente 6)

API FastAPI do diagnóstico de folhas de Coffea arabica, usada pelo coffea-web e pelo
coffea-mobile. O `POST /diagnostico` chama `inferencia.diagnosticar_arquivo` do coffea-ml (clone
irmão, `../coffea-ml`) e devolve o contrato dos frontends. O histórico (RF05) grava por folha em
SQLite (`coffea.db`). Detalhes no README.

## Regras
- Commits no imperativo, em português. Codex nunca faz commit, push, pull, merge, checkout de
  outras branches, reset --hard, force nem reescrita de histórico: o gestor commita pelo GitHub
  Desktop.
- Trabalhamos direto na `main`, sem branch nem PR (decisão do gestor, 15/10/2026; vale para todos
  os repositórios desde 16/10/2026).
- Nunca usar os conjuntos de teste fechados do coffea-ml (BRACOL de teste, `test/` do BRACOT,
  recortes de campo de teste), nem em testes, nem em medições.
- O modelo está congelado: não mudar parâmetros nem limiares, e não mexer no coffea-ml, no
  coffea-web nem no coffea-mobile a partir daqui. Exceção (decisão do gestor, 30/10/2026): o
  filtro de cor de folha do coffea-ml (passo 8 do CLAUDE.md de lá), sem troca de pesos.
- `requirements.txt` é mantido à mão (nunca `pip freeze`), e o ultralytics vai à parte com
  `--no-deps`. Nunca o `opencv-python`, só o headless.
- Schema do histórico mudou: README no mesmo commit. Nunca versionar pesos, banco nem `.env`.

## Rodar e testar
```powershell
pip install -r requirements.txt
pip install --no-deps ultralytics==8.4.175
pip install -r requirements-dev.txt
fastapi dev app/main.py --host 0.0.0.0
python -m pytest                        # modelo_real pulado sem os pesos
python scripts/medir_tempo.py --pasta ../coffea-ml/data/raw/bracot/bracot-data/train --amostra 30
```

## Variáveis (README, "Variáveis de ambiente"; modelo em .env.example)
`COFFEA_ML_DIR`, `COFFEA_PASTA_CLASSIFICADOR`, `COFFEA_PESOS_DETECTOR`, `COFFEA_VERIFICAR_PESOS`,
`COFFEA_CONCORRENCIA`, `COFFEA_CARREGAR_MODELO`, `COFFEA_DB`, `COFFEA_CORS_ORIGENS`. Produção (Docker +
Caddy no VPS): `deploy/DEPLOY.md`.

## Contrato
Sucesso: `{"status": "sucesso", "folhas": [{"id", "categoria", "severidade", "regiao"}, ...]}`,
com os extras do modelo repassados. Erro: `{"status": "erro", "tipo", "mensagem"}` em toda
resposta não-OK. Erro do modelo sai com 200; 413/415/422/503/500 vêm do backend (tabela no README).
