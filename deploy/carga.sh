#!/usr/bin/env bash
# Teste de carga do Cafélens: CHAMADAS envios em sequência ao POST /diagnostico, pelo Caddy (HTTPS),
# com as fotos da PASTA em ordem alfabética e em ciclo. Grava num CSV o tempo e o código HTTP de cada
# chamada e, a cada 10, a memória do contêiner da API; no fim, imprime o resumo. Só fotos de treino:
# nunca os conjuntos de teste fechados do coffea-ml (DEPLOY.md, "Teste de carga").
#
# Uso, na pasta deploy/, com a API no ar:
#   bash carga.sh PASTA [CHAMADAS] [URL]
#     CHAMADAS: padrão 1000. URL: padrão https://<DOMINIO do deploy/.env>.
#   Variáveis: SAIDA=pasta do CSV (padrão ../../medicoes); INSEGURO=1 aceita o certificado da CA
#   interna do Caddy (só na validação local, com https://localhost:18443).
set -euo pipefail
cd "$(dirname "$0")"

PASTA=${1:?uso: bash carga.sh PASTA [CHAMADAS] [URL]}
CHAMADAS=${2:-1000}
URL=${3:-https://$(sed -n 's/^DOMINIO=//p' .env | tr -d '\r')}
SAIDA=${SAIDA:-../../medicoes}
LIMITE=5  # RNF02, em segundos
OPCOES_CURL=()
[[ ${INSEGURO:-0} == 1 ]] && OPCOES_CURL+=(--insecure)

# A regra do scripts/medir_tempo.py (conferir_caminho): nenhuma pasta de teste fechado no caminho.
IFS=/ read -ra partes <<< "$(cd "$PASTA" && pwd -P | tr '[:upper:]' '[:lower:]')"
for parte in "${partes[@]}"; do
  if [[ $parte == test || $parte == teste || $parte == teste_* || $parte == *rotulagem_teste* ]]; then
    echo "recusado: $PASTA está numa pasta de teste fechado" >&2
    exit 1
  fi
done

# Ordem de bytes (LC_ALL=C), a mesma do sorted() do Python no medir_tempo.py.
mapfile -t FOTOS < <(find "$PASTA" -maxdepth 1 -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | LC_ALL=C sort)
(( ${#FOTOS[@]} > 0 )) || { echo "nenhuma foto JPG ou PNG em $PASTA" >&2; exit 1; }

CID=$(docker compose ps -q api)
[[ -n $CID ]] || { echo "a API não está no ar (docker compose ps)" >&2; exit 1; }
CGROUP=/sys/fs/cgroup/system.slice/docker-$CID.scope  # cgroup v2 com systemd (Ubuntu 24.04)

mib() {  # o valor de um arquivo do cgroup em MiB; vazio se não der para ler
  if [[ -r $1 ]]; then echo $(( $(<"$1") / 1048576 )); fi
}

memoria() {  # "memória,swap" do contêiner da API, em MiB
  if [[ -r $CGROUP/memory.current ]]; then
    echo "$(mib "$CGROUP/memory.current"),$(mib "$CGROUP/memory.swap.current")"
  else  # Docker Desktop: o cgroup fica dentro da VM; só a memória, pelo docker stats
    docker stats --no-stream --format '{{.MemUsage}}' "$CID" | awk '{
      v = $1 + 0
      if ($1 ~ /GiB/) v *= 1024; else if ($1 ~ /KiB/) v /= 1024; else if ($1 !~ /MiB/) v /= 1048576
      printf "%d,\n", v }'
  fi
}

mkdir -p "$SAIDA"
CSV=$SAIDA/carga-$(date +%Y%m%d-%H%M).csv
echo "chamada,foto,http,segundos,memoria_mib,swap_mib" > "$CSV"
echo "$CHAMADAS chamadas em $URL/diagnostico com ${#FOTOS[@]} fotos de $PASTA"
echo "CSV: $CSV"

inicio=$(date +%s)
for (( i = 1; i <= CHAMADAS; i++ )); do
  foto=${FOTOS[(i - 1) % ${#FOTOS[@]}]}
  resultado=$(curl -sS -o /dev/null -w '%{http_code} %{time_total}' --max-time 120 \
    "${OPCOES_CURL[@]}" -F "imagem=@$foto" "$URL/diagnostico" 2>/dev/null) || resultado="000 0"
  read -r codigo segundos <<< "$resultado"
  if (( i % 10 == 1 )); then amostra=$(memoria); else amostra=","; fi
  echo "$i,$(basename "$foto"),$codigo,$segundos,$amostra" >> "$CSV"
  if (( i % 50 == 0 )); then
    echo "$i/$CHAMADAS  última: HTTP $codigo em $segundos s  memória e swap (MiB): $(memoria)"
  fi
done
fim=$(date +%s)

echo
echo "Duração: $(( (fim - inicio) / 60 )) min $(( (fim - inicio) % 60 )) s"
echo "Códigos HTTP (quantidade e código):"
tail -n +2 "$CSV" | cut -d, -f3 | sort | uniq -c
tail -n +2 "$CSV" | cut -d, -f4 | sort -g | awk -v limite="$LIMITE" '
  { t[NR] = $1; if ($1 > limite) acima++ }
  END {
    n = NR
    mediana = (n % 2) ? t[(n + 1) / 2] : (t[n / 2] + t[n / 2 + 1]) / 2
    k = int(0.95 * n); if (k < 0.95 * n) k++  # p95 pelo posto mais próximo, como o medir_tempo.py
    printf "Tempo (s): mediana %.2f | p95 %.2f | máximo %.2f | acima de %d s: %d de %d\n",
      mediana, t[k], t[n], limite, acima, n
  }'
awk -F, -v total="$CHAMADAS" '
  BEGIN { swap = -1 }  # -1: sem leitura de swap (Docker Desktop)
  NR > 1 && $5 != "" {
    if (primeira == "") primeira = $5
    if ($5 > maximo) maximo = $5
    if ($6 != "" && $6 + 0 > swap) swap = $6 + 0
    if ($1 >= 50 && $1 <= 150) { base += $5; nb++ }
    if ($1 > total - 100) { ultimas += $5; nu++ }
  }
  END {
    printf "Memória da API (MiB): 1ª amostra %d | máximo %d | swap máximo %s\n",
      primeira, maximo, (swap < 0 ? "?" : swap)
    if (nb && nu)
      printf "Média das chamadas 50 a 150: %.0f MiB | das últimas 100: %.0f MiB (%+.1f%%)\n",
        base / nb, ultimas / nu, 100 * (ultimas / nu - base / nb) / (base / nb)
  }' "$CSV"
if [[ -r $CGROUP/memory.peak ]]; then
  echo "Pico do contêiner desde a subida (memory.peak): $(mib "$CGROUP/memory.peak") MiB"
  echo "Mortes por falta de memória (oom_kill): $(awk '$1 == "oom_kill" { print $2 }' "$CGROUP/memory.events")"
fi
echo "Reinícios do contêiner / OOMKilled: $(docker inspect -f '{{.RestartCount}} / {{.State.OOMKilled}}' "$CID")"
