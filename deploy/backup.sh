#!/usr/bin/env bash
# Backup do histórico: cópia datada e consistente do coffea.db em dados/backups/, com a API no ar (API
# de backup do sqlite3, rodada dentro do contêiner, que é o dono do banco).
# Uso, na pasta deploy/: bash backup.sh
# Baixar no PC, restaurar e agendar no cron: DEPLOY.md, "Backup do coffea.db".
set -euo pipefail
cd "$(dirname "$0")"

NOME=coffea-$(date +%Y%m%d-%H%M%S).db
docker compose exec -T api python -c '
import os
import sqlite3
import sys

os.makedirs("/dados/backups", exist_ok=True)
origem = sqlite3.connect("file:/dados/coffea.db?mode=ro", uri=True)  # ro: nunca cria um banco vazio
destino = sqlite3.connect(sys.argv[1])
origem.backup(destino)
destino.close()
origem.close()
' "/dados/backups/$NOME"
echo "backup gravado: dados/backups/$NOME"
