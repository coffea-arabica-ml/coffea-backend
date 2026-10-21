# syntax=docker/dockerfile:1
#
# Imagem da API do Cafélens: o coffea-backend e o código de inferência do coffea-ml, em CPU.
#
# Contexto do build: a pasta com os dois clones lado a lado (/opt/cafelens no servidor,
# coffea-arabica-ml/ no PC). O que entra no contexto está no Dockerfile.dockerignore, ao lado deste
# arquivo: só o código, o MANIFESTO.md dos pesos e dois manifestos de dados. Os pesos não entram na
# imagem: o docker-compose.yml os monta só-leitura nos caminhos padrão do coffea-ml, e o backend
# confere tamanho e SHA-256 contra o MANIFESTO.md a cada subida. Roteiro em deploy/DEPLOY.md.
FROM python:3.13.14-slim-trixie

ARG APP_UID=1000
ARG APP_GID=1000
ARG COMMIT_BACKEND=desconhecido
ARG COMMIT_ML=desconhecido
LABEL org.opencontainers.image.title="cafelens-api" \
      org.opencontainers.image.source="https://github.com/coffea-arabica-ml/coffea-backend" \
      org.opencontainers.image.licenses="AGPL-3.0" \
      cafelens.commit.backend="${COMMIT_BACKEND}" \
      cafelens.commit.ml="${COMMIT_ML}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    HOME=/tmp

WORKDIR /app/coffea-backend

# Dependências em três passos (README, "Dependências"):
# 1) torch e torchvision só CPU, do índice CPU do PyTorch (o do PyPI traz CUDA), nas versões lidas do
#    requirements.txt;
# 2) o requirements.txt, que não muda: o 2.13.0+cpu já atende o torch==2.13.0;
# 3) o ultralytics sem dependências (a versão é conferida abaixo contra a do coffea-ml).
COPY coffea-backend/requirements.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        $(grep -E '^(torch|torchvision)==' requirements.txt) \
 && pip install -r requirements.txt \
 && pip install --no-deps ultralytics==8.4.175

COPY coffea-ml/model/ /app/coffea-ml/model/
COPY coffea-ml/data/ /app/coffea-ml/data/
COPY coffea-ml/evaluation/ /app/coffea-ml/evaluation/
COPY coffea-backend/app/ ./app/
COPY coffea-backend/scripts/ ./scripts/

# Conferências que derrubam o build: torch sem CUDA; nenhum opencv-python (só o headless); a cadeia
# de inferência importa inteira, sem os pesos; o ultralytics é o do detector do coffea-ml e importa
# pelo mesmo caminho da subida (rede desligada). O pip freeze fica gravado na imagem.
RUN <<'EOF'
set -eu
export YOLO_CONFIG_DIR=/tmp
python - <<'PY'
import importlib.metadata as metadados
import sys

import torch

assert torch.version.cuda is None and torch.__version__.endswith("+cpu"), torch.__version__
for pacote in ("opencv-python", "opencv-contrib-python"):
    try:
        metadados.version(pacote)
    except metadados.PackageNotFoundError:
        continue
    sys.exit(f"{pacote} instalado: só o opencv-python-headless pode entrar")
sys.path.insert(0, "/app/coffea-ml/model")
import detector, inferencia, train  # noqa: E401,F401  (a cadeia inteira, sem carregar pesos)
assert metadados.version("ultralytics") == detector.VERSAO_ULTRALYTICS, metadados.version("ultralytics")
detector.importar_ultralytics()
print("imagem conferida: torch", torch.__version__, "ultralytics", detector.VERSAO_ULTRALYTICS,
      "Python", sys.version.split()[0])
PY
pip freeze > /app/pip-freeze.txt
rm -rf /tmp/Ultralytics
EOF

# Usuário sem root, com o UID/GID do usuário deploy do servidor (o dono de /opt/cafelens/dados).
# As pastas dos pesos são os pontos de montagem do compose.
RUN groupadd --gid "${APP_GID}" app \
 && useradd --uid "${APP_UID}" --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /dados /app/coffea-ml/model/runs/base_resnet50_bracol \
             /app/coffea-ml/model/runs/detector_base/weights \
 && chown app:app /dados
USER app

EXPOSE 8000
# Saudável só com o modelo carregado (GET /, bloco "modelo"): peso que não confere deixa "unhealthy".
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --start-interval=5s --retries=3 \
  CMD ["python", "-c", "import json, sys, urllib.request as u; sys.exit(0 if json.load(u.urlopen('http://127.0.0.1:8000/', timeout=4))['modelo']['carregado'] else 1)"]

# Um processo só (cada um carregaria o modelo). Só o Caddy alcança a API (rede interna), então os
# cabeçalhos X-Forwarded-* dele valem. O keep-alive (75 s) é maior que o do Caddy (30 s): o uvicorn
# nunca fecha uma conexão que o Caddy ainda vai reaproveitar.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-keep-alive", "75"]
