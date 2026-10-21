# Deploy do coffea-backend (VPS, Frente 10)

Roteiro da API do Cafélens em produção: `https://api.coffealab.tech`, 24 h por dia, de 21/10/2026 até
depois da apresentação de 06/11/2026, chamada pelo coffea-web (Vercel) e pelo app (APK). Substitui o
`PREPARAR_SERVIDOR.md` (roteiro executado em 21/10/2026), que foi revisado e incorporado nas seções 1
e 10.

> Nunca versione o IP do servidor, senhas, chaves privadas, o `deploy/.env`, os pesos nem o
> `coffea.db`. Abaixo, `<IP_DO_SERVIDOR>` e `<CHAVE_PRIVADA>` são marcadores, e o servidor aparece
> pelo alias `cafelens` do SSH (seção 1, passo 0): o IP fica só no `~/.ssh/config` do seu PC.
>
> Fotos para medir e testar: só de treino. Nunca os conjuntos de teste fechados do coffea-ml (o
> BRACOL de teste, a pasta `test/` do BRACOT e os recortes de campo de teste).

## Visão geral

```
Internet ──80/443──> caddy ──rede interna do Docker──> api:8000
                     HTTPS (Let's Encrypt)              uvicorn, 1 processo, 1 inferência por vez
                     corpo até 11 MiB, timeouts         código do backend e do coffea-ml na imagem
                     erros próprios no contrato         pesos só-leitura; /dados = coffea.db
```

| no servidor | o que é |
|---|---|
| `/opt/cafelens/coffea-backend/` | clone público num commit fixado; `deploy/.env` (fora do git) |
| `/opt/cafelens/coffea-ml/` | clone público num commit fixado, mais os 2 pesos copiados por `scp` |
| `/opt/cafelens/dados/` | `coffea.db` e `backups/` |
| `/opt/cafelens/fotos-treino/` | as 30 primeiras fotos do BRACOT de treino (medição e carga) |
| `/opt/cafelens/medicoes/` | CSVs do teste de carga |

- **Imagem** (`deploy/Dockerfile`): Python 3.13.14, torch e torchvision só CPU (índice CPU do
  PyTorch), o `requirements.txt` e o ultralytics com `--no-deps`; usuário sem root; healthcheck no
  `GET /` (saudável só com `carregado=true`). O contexto do build é `/opt/cafelens`, e o
  `deploy/Dockerfile.dockerignore` deixa entrar só o código, o `MANIFESTO.md` e dois manifestos de
  dados.
- **Pesos:** montados só-leitura, por arquivo, nos caminhos padrão do coffea-ml. O backend confere
  tamanho e SHA-256 contra o `MANIFESTO.md` a cada subida (`COFFEA_VERIFICAR_PESOS=1`).
- **Compose** (`deploy/docker-compose.yml`): só o Caddy publica portas (80 e 443). O Docker passa
  por cima do `ufw` nas portas publicadas; por isso a API não publica nenhuma e fica numa rede
  interna sem saída para a internet. Limites da API: 2,5 GiB de RAM, mais 1 GiB de swap, e o vCPU
  inteiro. Logs com rotação (3 × 10 MB por serviço).
- **Caddy** (`deploy/Caddyfile`): limites e timeouts explicados no próprio arquivo. Erros do Caddy
  (corpo acima de 11 MiB, API fora ou reiniciando) saem no contrato (`{"status": "erro", ...}`), mas
  sem CORS.

## 1. Preparar o servidor (Ubuntu 24.04 LTS, VPS Hostinger KVM 1)

| Item | Valor observado |
|---|---|
| Provedor / plano | Hostinger, VPS KVM 1 (1 vCPU, 4 GB de RAM, 50 GB NVMe), plano de 1 mês |
| Região | Brasil |
| Sistema | Ubuntu 24.04.5 LTS, kernel 6.8.0-147 |
| Domínio | `coffealab.tech` (API em `api.coffealab.tech`, registro DNS tipo A, TTL 300) |
| Docker | docker-ce 29.9.2, plugin compose 5.6.1 |

Não rode `do-release-upgrade` (o banner oferece o Ubuntu 26.04): o projeto fica no 24.04 LTS.

### 0. No PC: chave SSH e alias

Chave criada no Windows (PowerShell), com a parte pública cadastrada no painel do VPS:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\<CHAVE_PRIVADA>" -C "cafelens-vps"
Get-Content "$env:USERPROFILE\.ssh\<CHAVE_PRIVADA>.pub" | Set-Clipboard
```

O arquivo `.pub` é a chave pública (vai para o painel). O arquivo sem `.pub` é a privada e nunca sai
do computador.

Aliases no `~/.ssh/config` do PC (`notepad "$env:USERPROFILE\.ssh\config"`; crie o arquivo se não
existir). O IP fica só aqui, e o resto do roteiro usa `cafelens`:

```
Host cafelens
    HostName <IP_DO_SERVIDOR>
    User deploy
    IdentityFile ~/.ssh/<CHAVE_PRIVADA>
    IdentitiesOnly yes

Host cafelens-root
    HostName <IP_DO_SERVIDOR>
    User root
    IdentityFile ~/.ssh/<CHAVE_PRIVADA>
    IdentitiesOnly yes
```

### 1. Atualizar o sistema (como root)

```powershell
ssh cafelens-root
```

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get -y upgrade
timedatectl set-timezone America/Sao_Paulo
```

### 2. Usuário `deploy` (como root)

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
echo 'deploy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-deploy
chmod 440 /etc/sudoers.d/90-deploy && visudo -cf /etc/sudoers.d/90-deploy   # deve dizer: parsed OK
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
mkdir -p /opt/cafelens && chown deploy:deploy /opt/cafelens
```

O `deploy` não tem senha, então o `sudo` precisa do `NOPASSWD`. Como ele também entra no grupo
`docker` (passo 5), que já equivale a root, isso não abre nada a mais.

Teste em outro terminal, sem fechar o do root:

```powershell
ssh cafelens
```

```bash
sudo whoami   # deve responder: root
```

### 3. Atualização final, ferramentas e reinício (como deploy)

```bash
sudo DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade
sudo apt-get install -y git tmux
sudo reboot
```

Depois de 1 minuto, entre de novo. Confira o fuso: `timedatectl | grep "Time zone"`.
Pacotes "adiados por phasing" (cloud-init, glib, tmux) são normais e chegam depois.

### 4. Swap de 2 GB

O modelo chegou a 2,4 GB de memória privada no Windows (pico); a medida do Linux sai do teste de
carga (seção 4).

```bash
swapon --show   # vazio: criar
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf && sudo sysctl --system > /dev/null
free -h   # deve mostrar: Swap 2.0Gi
```

### 5. Docker (repositório oficial)

```bash
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker deploy
sudo docker run --rm hello-world   # deve imprimir: Hello from Docker!
```

O grupo `docker` só vale no próximo login do `deploy`. Docker no grupo `docker` equivale a acesso de
root ao servidor: só o usuário `deploy` entra nele.

Configuração do daemon: com `live-restore`, os contêineres continuam no ar se o `dockerd` reiniciar
(numa atualização, por exemplo); a rotação de logs vale para qualquer contêiner.

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
sudo systemctl restart docker
sudo docker info --format '{{.LiveRestoreEnabled}}'   # deve dizer: true
systemctl is-enabled docker containerd                 # deve dizer: enabled (duas vezes)
```

### 6. Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Atenção: portas publicadas pelo Docker passam por cima do `ufw`. O compose do projeto publica só 80
e 443 (Caddy), e a API fica na rede interna do Docker. Não acrescente `ports:` na API.

### 7. SSH só por chave

```bash
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' | sudo tee /etc/ssh/sshd_config.d/00-cafelens.conf
sudo sshd -t && sudo systemctl reload ssh
sudo sshd -T | grep -E "^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin)"
```

Saída esperada: `permitrootlogin without-password`, `passwordauthentication no`,
`kbdinteractiveauthentication no`. O root continua entrando, só com chave (decisão do gestor). O
arquivo se chama `00-...` de propósito: no `sshd`, vale o primeiro valor lido, e o
`50-cloud-init.conf` poderia religar a senha. Antes de fechar a sessão, abra outro terminal e
confirme que o login por chave ainda funciona.

### 8. Atualizações durante o mês

As atualizações de segurança do Ubuntu continuam automáticas. As do Docker ficam travadas até depois
da apresentação: uma atualização do `docker-ce` reinicia o daemon.

```bash
systemctl is-active unattended-upgrades   # deve dizer: active
sudo apt-mark hold docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
apt-mark showhold
```

Depois da apresentação: `sudo apt-mark unhold` com a mesma lista.

### 9. Verificação final

- [ ] `ssh cafelens` entra só com a chave.
- [ ] `ssh -o PubkeyAuthentication=no deploy@<IP_DO_SERVIDOR>` responde `Permission denied (publickey)`.
- [ ] `nslookup api.coffealab.tech 8.8.8.8` responde o IP do servidor.
- [ ] `free -h` mostra 2,0 GiB de swap; `docker --version` e `docker compose version` respondem.
- [ ] `sudo ufw status` mostra só 22, 80 e 443.
- [ ] `docker info --format '{{.LiveRestoreEnabled}}'` responde `true`; `apt-mark showhold` lista os
      pacotes do Docker.
- [ ] `git --version` e `tmux -V` respondem.

## 2. Primeira instalação

### 2.1 Clones (no servidor)

Os commits fixados: o do coffea-backend que tem esta pasta `deploy/`, e o do coffea-ml com o
`MANIFESTO.md` dos pesos congelados (o mesmo de `dd1969f`; use o último da `main`).

```bash
cd /opt/cafelens
git clone https://github.com/coffea-arabica-ml/coffea-backend.git
git clone https://github.com/coffea-arabica-ml/coffea-ml.git
git -C coffea-backend -c advice.detachedHead=false checkout --detach <COMMIT_DO_BACKEND>
git -C coffea-ml -c advice.detachedHead=false checkout --detach <COMMIT_DO_ML>
mkdir -p dados/backups fotos-treino medicoes && chmod 700 dados
```

### 2.2 Pesos (do PC para o servidor) e SHA-256

No PC (PowerShell), confira os hashes antes de copiar. O PowerShell mostra em maiúsculas; compare com
a tabela do `coffea-ml/model/pesos/MANIFESTO.md` sem olhar a caixa.

```powershell
cd "$env:USERPROFILE\Documents\coffea-arabica-ml\coffea-ml"
Get-FileHash -Algorithm SHA256 model\runs\base_resnet50_bracol\melhor.pt, model\runs\detector_base\weights\last.pt | Format-List Hash, Path
ssh cafelens "mkdir -p /opt/cafelens/coffea-ml/model/runs/base_resnet50_bracol /opt/cafelens/coffea-ml/model/runs/detector_base/weights"
scp model\runs\base_resnet50_bracol\melhor.pt cafelens:/opt/cafelens/coffea-ml/model/runs/base_resnet50_bracol/
scp model\runs\detector_base\weights\last.pt cafelens:/opt/cafelens/coffea-ml/model/runs/detector_base/weights/
```

No servidor, compare com o manifesto do commit fixado (o backend faz a mesma conferência a cada
subida):

```bash
cd /opt/cafelens/coffea-ml
for f in model/runs/base_resnet50_bracol/melhor.pt model/runs/detector_base/weights/last.pt; do
  esperado=$(grep -F "| \`$f\` |" model/pesos/MANIFESTO.md | grep -oE '[0-9a-f]{64}')
  obtido=$(sha256sum "$f" | cut -d' ' -f1)
  if [ -n "$esperado" ] && [ "$esperado" = "$obtido" ]; then echo "OK   $f"; else echo "ERRO $f"; fi
done
```

Os dois têm de dar `OK`.

### 2.3 Fotos de treino (do PC para o servidor)

As 30 primeiras, em ordem alfabética, do BRACOT de **treino** (as mesmas da medição do RNF02 no PC;
os nomes são datas, e a ordem do PowerShell é a do Python). São ~120 MB.

```powershell
cd "$env:USERPROFILE\Documents\coffea-arabica-ml\coffea-ml"
$fotos = Get-ChildItem data\raw\bracot\bracot-data\train -Filter *.jpg | Sort-Object Name | Select-Object -First 30
scp $fotos.FullName cafelens:/opt/cafelens/fotos-treino/
```

### 2.4 `deploy/.env` (no servidor)

```bash
cd /opt/cafelens/coffea-backend/deploy
cp .env.example .env && chmod 600 .env
sed -i "s/^COMMIT_BACKEND=.*/COMMIT_BACKEND=$(git -C .. rev-parse --short HEAD)/; s/^COMMIT_ML=.*/COMMIT_ML=$(git -C ../../coffea-ml rev-parse --short HEAD)/" .env
id -u; id -g   # se não for 1000 e 1000, ajuste APP_UID e APP_GID no .env
nano .env      # COFFEA_CORS_ORIGENS: a URL exata do coffea-web na Vercel, sem barra no fim
```

Guarde uma cópia do `.env` no PC, fora de qualquer repositório (seção 10).

### 2.5 Conferir, construir e subir

```bash
cd /opt/cafelens/coffea-backend/deploy
docker compose config --quiet && echo "compose OK"
docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose build api      # o 1º build baixa ~1 GB; no fim do log: "imagem conferida: torch ...+cpu"
docker compose up -d --wait   # volta quando a API fica healthy (modelo carregado e pesos conferidos)
docker compose ps
docker compose logs caddy | grep -i "certificate obtained"
```

No log do build, a linha `transferring context` deve ficar em poucos MB: é o
`Dockerfile.dockerignore` deixando de fora os dados e os pesos.

### 2.6 Testes com curl (no servidor)

```bash
cd /opt/cafelens/coffea-backend/deploy
D=https://$(sed -n 's/^DOMINIO=//p' .env)
O=$(sed -n 's/^COFFEA_CORS_ORIGENS=//p' .env | cut -d, -f1)
F=$(ls -d /opt/cafelens/fotos-treino/* | head -1)
curl -s "$D/"; echo
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' -F "imagem=@$F" "$D/diagnostico"
echo texto > /tmp/texto.jpg && curl -s -w ' %{http_code}\n' -F imagem=@/tmp/texto.jpg "$D/diagnostico"
truncate -s 10500K /tmp/medio.jpg && curl -s -D - -o /dev/null -H "Origin: $O" -F imagem=@/tmp/medio.jpg "$D/diagnostico" | grep -iE '^HTTP|^access-control-allow-origin'
truncate -s 12M /tmp/grande.jpg && curl -s -w ' %{http_code}\n' -F imagem=@/tmp/grande.jpg "$D/diagnostico"
curl -s -w ' %{http_code}\n' -X POST "$D/diagnostico"
curl -s -D - -o /dev/null -H "Origin: https://outro.example" "$D/" | grep -ic '^access-control-allow-origin'
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "http://${D#https://}/"
rm -f /tmp/texto.jpg /tmp/medio.jpg /tmp/grande.jpg
```

| comando | esperado |
|---|---|
| `GET /` | `"carregado": true`, `"pesos_verificados": true`, `"motivo": null` |
| foto de treino | `200` em poucos segundos |
| texto com nome `.jpg` | `{"status": "erro", "tipo": "formato_invalido", ...} 415` |
| 10,5 MB com `Origin` permitida | `HTTP/2 413` e `access-control-allow-origin` (o 413 do backend) |
| 12 MB | `{"status": "erro", "tipo": "arquivo_muito_grande", ...} 413` (o do Caddy) |
| sem o campo `imagem` | `{"status": "erro", "tipo": "formato_invalido", ...} 422` |
| `Origin` não permitida | `0` (nenhum cabeçalho de CORS) |
| `http://` | `308 https://...` |

## 3. Medição do RNF02 (≤ 5 s) no servidor

O `scripts/medir_tempo.py` sobe o próprio servidor dentro de um contêiner avulso, com o histórico num
banco temporário (o `coffea.db` não é tocado), e recusa caminhos e SHA-256 de teste fechado. A API
para antes, para não haver dois modelos na memória (o site fica fora por ~2 min).

```bash
cd /opt/cafelens/coffea-backend/deploy
docker compose stop api
docker compose run --rm --no-deps -v /opt/cafelens/fotos-treino:/fotos:ro api \
  python scripts/medir_tempo.py --pasta /fotos --amostra 30
docker compose start api
```

O contêiner avulso aparece como `unhealthy` enquanto mede (o healthcheck olha a porta 8000, e o
script usa a 8765): é esperado. Mande a tabela impressa para o README ("Medição do RNF02").

## 4. Teste de carga

1.000 chamadas em sequência, pelo Caddy, com as fotos de treino em ciclo: ~35 a 50 min. Rode dentro
do `tmux`, para uma queda do SSH não interromper.

```bash
tmux new -s carga
cd /opt/cafelens/coffea-backend/deploy
bash carga.sh /opt/cafelens/fotos-treino 1000
```

`Ctrl+B` e depois `D` saem do tmux sem parar o teste; `tmux attach -t carga` volta. Em outra sessão
SSH, acompanhe: `docker stats`, `free -m`, `vmstat 5`.

O script grava `/opt/cafelens/medicoes/carga-AAAAMMDD-HHMM.csv` e imprime no fim: códigos HTTP;
mediana, p95 e máximo do tempo; chamadas acima de 5 s; memória da API (1ª amostra, máximo, swap,
média das chamadas 50 a 150 contra a das últimas 100); `memory.peak` e `oom_kill` do cgroup; reinícios
e `OOMKilled` do contêiner.

**Passa se:** todas as chamadas dão HTTP 200; nenhum reinício nem `oom_kill`; swap da API perto de 0;
a média das últimas 100 chamadas fica até ~10% acima da das chamadas 50 a 150 (sem vazamento).

## 5. Começar limpo, aquecer e divulgar

Depois da medição e da carga (decisão do gestor: o histórico da apresentação começa limpo), arquive o
banco dos testes e suba vazio. O backend cria as tabelas na subida.

```bash
cd /opt/cafelens/coffea-backend/deploy
bash backup.sh
docker compose stop api
mv ../../dados/coffea.db ../../dados/backups/coffea-testes-$(date +%Y%m%d).db
docker compose up -d --no-build --wait
```

Aquecimento: a 1ª chamada depois de cada subida é a mais lenta. Faça 2 ou 3 com a 1ª foto de treino
(ficam 2 ou 3 diagnósticos no histórico):

```bash
F=$(ls -d /opt/cafelens/fotos-treino/* | head -1)
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' -F "imagem=@$F" "https://$(sed -n 's/^DOMINIO=//p' .env)/diagnostico"
```

Só então:
- **Vercel (coffea-web):** `VITE_API_MODE=http` e `VITE_API_URL=https://api.coffealab.tech` nas
  variáveis do projeto, e um novo deploy (o Vite lê as variáveis na build).
- **APK (coffea-mobile):** gerado com `EXPO_PUBLIC_API_MODE=http` e
  `EXPO_PUBLIC_API_URL=https://api.coffealab.tech`. Atenção: o perfil `preview` do `eas.json` fixa
  `EXPO_PUBLIC_API_MODE=mock`.
- Divulgar a URL.

## 6. Operação

```bash
cd /opt/cafelens/coffea-backend/deploy
docker compose ps                              # api "healthy" e caddy "running"
docker compose logs -f --tail 200 -t api       # -t: hora (UTC) de cada linha; Ctrl+C sai
docker compose logs -f --tail 200 -t caddy
docker stats --no-stream
docker compose restart api                     # ~10 a 30 s de 502 enquanto o modelo carrega; aqueça depois
curl -s "https://$(sed -n 's/^DOMINIO=//p' .env)/"; echo
```

Depois de qualquer reinício (do contêiner ou do servidor), o compose sobe sozinho
(`restart: unless-stopped`), e a 1ª chamada sai fria: aqueça (seção 5).

## 7. Atualizar versão

Evite perto da apresentação: o build ocupa o vCPU e deixa a API lenta.

```bash
cd /opt/cafelens
git -C coffea-backend fetch && git -C coffea-backend -c advice.detachedHead=false checkout --detach <NOVO_COMMIT>
# se o coffea-ml mudou: o mesmo com coffea-ml (e confira o SHA-256 dos pesos, seção 2.2)
cd coffea-backend/deploy
grep '^COMMIT_' .env | tee -a ../../medicoes/versoes.txt   # anota a versão atual, para o rollback
sed -i "s/^COMMIT_BACKEND=.*/COMMIT_BACKEND=$(git -C .. rev-parse --short HEAD)/; s/^COMMIT_ML=.*/COMMIT_ML=$(git -C ../../coffea-ml rev-parse --short HEAD)/" .env
docker compose build api
docker compose up -d --no-build --wait
```

Depois, aqueça (seção 5). Cada par de commits vira uma imagem `cafelens-api:<backend>-<ml>`, e as
anteriores ficam no disco para o rollback.

## 8. Rollback

```bash
cd /opt/cafelens/coffea-backend/deploy
docker image ls cafelens-api        # as versões disponíveis
cat ../../medicoes/versoes.txt      # as anotadas na seção 7
nano .env                           # COMMIT_BACKEND e COMMIT_ML da versão anterior
docker compose up -d --no-build --wait
```

O `--no-build` falha se a imagem não existir, em vez de construir uma imagem com o nome da versão
antiga e o código da atual. Se a mudança foi no `docker-compose.yml` ou no `Caddyfile`, volte também
o clone: `git -C .. -c advice.detachedHead=false checkout --detach <COMMIT_ANTERIOR>`. Imagens velhas:
`docker image rm cafelens-api:<versão>` (guarde pelo menos as duas últimas).

## 9. Backup do `coffea.db`

O `deploy/backup.sh` grava uma cópia consistente, com a API no ar, em
`/opt/cafelens/dados/backups/coffea-AAAAMMDD-HHMMSS.db`:

```bash
cd /opt/cafelens/coffea-backend/deploy
bash backup.sh
```

Baixar no PC (PowerShell, na pasta onde quer o arquivo):

```powershell
ssh cafelens "ls -t /opt/cafelens/dados/backups | head -5"
scp cafelens:/opt/cafelens/dados/backups/<ARQUIVO> .
```

Restaurar:

```bash
cd /opt/cafelens/coffea-backend/deploy
docker compose stop api
cp ../../dados/backups/<ARQUIVO> ../../dados/coffea.db
docker compose up -d --no-build --wait
```

Agendar (opcional), com `crontab -e` no usuário `deploy`: backup diário às 3h30 e remoção dos
backups datados com mais de 14 dias (os `coffea-testes-*` ficam).

```
30 3 * * * bash /opt/cafelens/coffea-backend/deploy/backup.sh >> /opt/cafelens/dados/backups/backup.log 2>&1
45 3 * * * find /opt/cafelens/dados/backups -name 'coffea-2*.db' -mtime +14 -delete
```

## 10. Recriar do zero (ex.: troca de região do VPS, que reinstala o sistema)

1. Antes: baixe o backup do `coffea.db` (seção 9) e uma cópia do `.env`
   (`scp cafelens:/opt/cafelens/coffea-backend/deploy/.env .\deploy.env`, fora de qualquer
   repositório). Reinstalar apaga tudo, inclusive backups e snapshots do painel.
2. Reinstale o sistema pelo painel e cadastre a chave pública.
3. Se o IP mudou: atualize o registro DNS `A` de `api` (TTL 300) e o `HostName` do
   `~/.ssh/config`. A chave do servidor muda de qualquer forma: `ssh-keygen -R <IP_DO_SERVIDOR>` no PC.
4. Refaça a seção 1 (passos 1 a 9).
5. Refaça a seção 2 (clones, pesos com SHA-256, fotos, `.env` a partir da cópia) e restaure o banco
   (seção 9).
6. O Let's Encrypt emite no máximo 5 certificados iguais por semana: recriar várias vezes na mesma
   semana pode bater o limite (o log do Caddy diz).

## 11. Problemas comuns

| sintoma | causa provável | o que fazer |
|---|---|---|
| HTTPS não sobe; o log do Caddy fala em "challenge" | DNS ainda não aponta para o servidor, ou porta 80 fechada | `nslookup api.coffealab.tech 8.8.8.8`; `sudo ufw status`; `docker compose logs caddy` |
| 502 com `erro_desconhecido` logo depois de subir | o modelo ainda está carregando | esperar o `healthy` em `docker compose ps` |
| `GET /` com `"carregado": false` | o `motivo` diz: peso ausente ou que não confere com o `MANIFESTO.md` | seção 2.2; `docker compose logs api` |
| `unhealthy` em `docker compose ps` | o mesmo de cima | o mesmo de cima |
| `up` falha com "bind source path does not exist" | peso ausente no caminho padrão | seção 2.2 |
| API não sobe: "COFFEA_CORS_ORIGENS deve listar origens..." | marcador do `.env.example`, barra no fim ou caminho | corrigir o `.env` e `docker compose up -d --no-build --wait` |
| no navegador, "falha de conexão", mas o `curl` funciona | a origem do site não está no `COFFEA_CORS_ORIGENS` (preview da Vercel tem outra URL) | conferir a URL exata e reiniciar a API |
| a API reinicia sozinha; `OOMKilled` true | memória | `docker inspect -f '{{.RestartCount}} {{.State.OOMKilled}}' $(docker compose ps -q api)`; seção 4 |
| diagnóstico demora mais de 30 s no site | fila: uma inferência por vez | esperado com muitos envios juntos; o servidor processa todos |

## 12. Checklist do dia 06/11

- **Na véspera:** backup baixado no PC; `docker compose ps` com a API `healthy`; `GET /` com
  `carregado` true; 1 diagnóstico pelo site e 1 pelo APK; `df -h` e `free -m` com folga; validade do
  certificado: `echo | openssl s_client -connect api.coffealab.tech:443 2>/dev/null | openssl x509 -noout -enddate`.
- **1 h antes:** aquecimento (seção 5); site e APK diagnosticando, pelo Wi-Fi do local e pela rede
  móvel.
- **Não fazer no dia:** build, atualizar versão, `apt upgrade`, reiniciar o servidor.
- **Plano B:** o backend no PC (README, "Rodando localmente") e os frontends em modo `http` com o IP
  local.

## Validação local (Docker Desktop, no PC)

Antes de ir ao servidor, a mesma imagem roda no Docker Desktop (WSL2). O `compose.local.yml` publica
o Caddy só em `127.0.0.1:18080/18443` e prende a API a 1 CPU, como o VPS.

1. Copie o `deploy\.env.example` para `deploy\.env` (fora do git) e mude: `DOMINIO=localhost`,
   `COFFEA_CORS_ORIGENS=http://localhost:5173`, e os commits de `git -C .. rev-parse --short HEAD` e
   `git -C ..\..\coffea-ml rev-parse --short HEAD`. Salve com fim de linha LF (VS Code: canto
   inferior direito).
2. Com o Docker Desktop aberto, na pasta `coffea-backend\deploy` (PowerShell):

```powershell
New-Item -ItemType Directory -Force ..\..\dados\backups, ..\..\medicoes | Out-Null
docker compose -f docker-compose.yml -f compose.local.yml build api
docker compose -f docker-compose.yml -f compose.local.yml up -d --wait
curl.exe -sk https://localhost:18443/
```

- **RNF02 com 1 CPU:** pare a API (`... stop api`) e rode o `medir_tempo.py` num contêiner avulso,
  com a pasta de treino do BRACOT montada:
  `docker compose -f docker-compose.yml -f compose.local.yml run --rm --no-deps -v "$((Resolve-Path ..\..\coffea-ml\data\raw\bracot\bracot-data\train).Path):/fotos:ro" api python scripts/medir_tempo.py --pasta /fotos --amostra 30`.
- **Carga curta (Git Bash):** `INSEGURO=1 bash carga.sh "C:/Users/<você>/Documents/coffea-arabica-ml/coffea-ml/data/raw/bracot/bracot-data/train" 100 https://localhost:18443`
  (a memória vem do `docker stats`; o Docker Desktop não expõe o cgroup).
- **No fim:** `docker compose -f docker-compose.yml -f compose.local.yml down` (a imagem fica; nunca `-v`
  no servidor). A pasta `coffea-arabica-ml\dados` local fica fora dos repositórios.
