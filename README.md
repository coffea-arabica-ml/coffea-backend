# coffea-backend

API que expõe o modelo de classificação de estresses bióticos em folhas
de Coffea arabica, consumida pelo coffea-web e pelo coffea-mobile.

A rota de diagnóstico chama a inferência real do coffea-ml (Frente 9) e devolve o
diagnóstico por folha no contrato dos frontends. O histórico (RF05) guarda o resultado de
cada folha em SQLite.

## Stack
Python 3.13 + FastAPI. Ver justificativa completa no Guia Técnico (Drive,
pasta 06 - Backend).

- **Modelo:** o do coffea-ml (PyTorch + ultralytics), em CPU, carregado do clone local.
- **Histórico:** SQLite via SQLAlchemy.

## Rodando localmente
Os dois repositórios ficam lado a lado, e os pesos ficam no coffea-ml (ver "Pesos do modelo"):

```
coffea-arabica-ml/
  coffea-backend/
  coffea-ml/
```

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install --no-deps ultralytics==8.4.175
fastapi dev app/main.py --host 0.0.0.0
```

A instalação tem dois passos. O ultralytics entra sem dependências (ver "Dependências").

Documentação interativa das rotas em http://127.0.0.1:8000/docs. O roteiro de teste pelo
Swagger está em [GUIA_TESTE.md](GUIA_TESTE.md).

O `--host 0.0.0.0` é necessário para o coffea-mobile alcançar o servidor
pela rede Wi-Fi local.

- **Subida:** o servidor confere os pesos e carrega o modelo antes de aceitar requisições
  (6,9 s nesta máquina). O `GET /` mostra se o modelo carregou e, se não, o motivo.
- **Reload:** o `fastapi dev` reinicia o servidor a cada `.py` salvo, e cada reinício carrega o
  modelo de novo. Para mexer só no front, use `COFFEA_CARREGAR_MODELO=0` (o servidor sobe na
  hora e o `POST /diagnostico` responde 503). Para uma apresentação, sem reload:
  `fastapi run app/main.py --host 0.0.0.0`.
- **Frontends em modo real:** no coffea-web, `VITE_API_MODE=http` e
  `VITE_API_URL=http://localhost:8000`. No coffea-mobile, `EXPO_PUBLIC_API_MODE=http` e
  `EXPO_PUBLIC_API_URL=http://<IP do PC>:8000`. O IP do PC é o "Endereço IPv4" do Wi-Fi no
  `ipconfig`.

### Celular na mesma rede: firewall do Windows
Orientação para quem vai apresentar. Os comandos mudam a configuração do Windows: rode-os você
mesmo, no PowerShell **como administrador**.

1. Confira que o Wi-Fi está como rede **Privada**. Em `Get-NetConnectionProfile`, o
   `NetworkCategory` tem de ser `Private`. Pela tela: Configurações > Rede e Internet > Wi-Fi >
   (a rede) > Tipo de perfil de rede. Só marque como Privada uma rede em que você confia.
2. Libere a porta 8000 só no perfil Privado:
   ```powershell
   New-NetFirewallRule -DisplayName "coffea-backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```
3. Depois da apresentação, remova a regra:
   ```powershell
   Remove-NetFirewallRule -DisplayName "coffea-backend 8000"
   ```

**Isolamento de clientes.** Muitas redes Wi-Fi (é comum em faculdade) não deixam um aparelho
falar com outro. Nelas, o celular não alcança o PC mesmo com a regra. Use o hotspot do celular
ou outra rede.

## Pesos do modelo
- **Onde ficam:** no coffea-ml, fora do git. O classificador é
  `model/runs/base_resnet50_bracol/melhor.pt`, e o detector,
  `model/runs/detector_base/weights/last.pt`. Nome, tamanho e SHA-256 de cada um estão em
  `coffea-ml/model/pesos/MANIFESTO.md`.
- **Conferência na subida:** com `COFFEA_VERIFICAR_PESOS=1` (o padrão), o backend compara o
  tamanho e o SHA-256 dos dois arquivos com a tabela do manifesto, lida a cada subida. Se não
  conferir, o servidor sobe sem modelo: o `GET /` mostra o motivo, e o `POST /diagnostico`
  responde 503.
- **Conferência à mão:** o comando do manifesto, na pasta do coffea-ml:
  ```
  python -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" model/runs/base_resnet50_bracol/melhor.pt
  ```
  Repita com `model/runs/detector_base/weights/last.pt` e compare com a tabela.
- **Pesos em outro lugar:** `COFFEA_PASTA_CLASSIFICADOR` (a pasta do `melhor.pt`) e
  `COFFEA_PESOS_DETECTOR` (o arquivo do detector). Fora do coffea-ml, a conferência acha a
  linha do manifesto pelo nome do arquivo.
- **Modelo congelado:** o backend não muda parâmetros nem limiares. Ele chama só
  `inferencia.diagnosticar_arquivo(bytes, modelos=...)`, com a configuração padrão. Os modelos
  vão explícitos para valerem os caminhos acima.

## Variáveis de ambiente
Lidas na subida, do ambiente e do `.env` da raiz (fora do git; modelo em
[.env.example](.env.example)). O ambiente tem prioridade sobre o `.env`. Caminhos relativos valem
a partir da raiz deste repositório. Valor inválido impede a subida, com o nome da variável.

| variável | padrão | o que faz |
|---|---|---|
| `COFFEA_ML_DIR` | `../coffea-ml` | clone do coffea-ml |
| `COFFEA_PASTA_CLASSIFICADOR` | a do inferencia | pasta do `melhor.pt` |
| `COFFEA_PESOS_DETECTOR` | a do inferencia | arquivo `last.pt` do detector |
| `COFFEA_VERIFICAR_PESOS` | `1` | confere tamanho e SHA-256 contra o manifesto |
| `COFFEA_CONCORRENCIA` | `1` | inferências ao mesmo tempo (semáforo). Não aumente sem testar: o YOLO do ultralytics não é thread-safe |
| `COFFEA_CARREGAR_MODELO` | `1` | `0` sobe sem modelo, e o `POST /diagnostico` responde 503 |
| `COFFEA_DB` | `coffea.db` | banco do histórico |

## Rotas
- `GET /` — healthcheck, com o estado do modelo
- `POST /diagnostico` — recebe a foto no campo `imagem` (multipart) e devolve o diagnóstico
  por folha (contrato abaixo)
- `GET /diagnosticos?limit=100` — histórico, dos mais recentes para os mais antigos (`limit`
  de 1 a 500)
- `GET /diagnosticos/{id}` — um diagnóstico do histórico

O `GET /` mantém o `status` e a `mensagem` do esqueleto e acrescenta o bloco `modelo`, sem
caminhos do disco:

```json
{"status": "ok", "mensagem": "coffea-backend no ar",
 "modelo": {"carregado": true, "classificador": "base_resnet50_bracol",
            "detector": "detector_base", "pesos_verificados": true, "motivo": null}}
```

## Contrato do `POST /diagnostico`
É o contrato do coffea-web (`docs/frontend-reference/03-contrato-api-mock.md` e
`src/api/types.ts`) e do coffea-mobile. A resposta é o dicionário de
`inferencia.diagnosticar_arquivo`, sem nenhum valor alterado.

**Sucesso** (HTTP 200):

```json
{"status": "sucesso",
 "folhas": [{"id": "folha-1", "categoria": "ferrugem", "severidade": "baixa",
             "regiao": {"x": 0.412, "y": 0.377, "raio": 0.142},
             "confianca": 0.81, "scoreDeteccao": 0.93, "caixa": [0.28, 0.21, 0.55, 0.52],
             "cortadaNaBorda": false}],
 "detalhes": {"plano": "deteccao", "...": "..."}}
```

- **`categoria`:** `saudavel`, `ferrugem`, `bicho_mineiro`, `cercosporiose` ou `phoma`.
- **`severidade`:** `saudavel`, `muito_baixa`, `baixa`, `alta` ou `muito_alta`.
- **`regiao`:** o centro é relativo à largura e à altura da foto; o raio, à menor dimensão.
- **Extras:** `confianca`, `scoreDeteccao`, `caixa`, `cortadaNaBorda` e `detalhes` vêm do modelo,
  e os frontends os ignoram. O significado de cada um está no README do coffea-ml, seção
  "Interface para o backend".
- **Sem `imagemUrl`:** os frontends usam a foto local, e o backend não guarda fotos.

**Erro:** `{"status": "erro", "tipo": ..., "mensagem": ...}`, com a mensagem em português e sem
detalhes internos. Os erros do modelo podem trazer também `detalhes`.

| HTTP | `tipo` | quando |
|---|---|---|
| 200 | `planta_nao_identificada` | o modelo não achou folha de café utilizável |
| 200 | `baixa_confianca` | todas as folhas ficaram abaixo do corte (RF07), ou só há pedaços de folha |
| 200 | `formato_invalido` | o arquivo começa como JPG ou PNG, mas não decodifica |
| 200 | `arquivo_muito_grande` | mais de 64 megapixels, lidos do cabeçalho |
| — | `especie_incorreta` | não é produzido hoje: não há dados de outras plantas para treinar essa recusa |
| 413 | `arquivo_muito_grande` | arquivo acima de 10 MB (10 × 1024 × 1024 bytes) |
| 415 | `formato_invalido` | não é JPG (começa com `FF D8 FF`) nem PNG (`89 50 4E 47 0D 0A 1A 0A`) |
| 422 | `formato_invalido` | sem o campo `imagem`, ou arquivo vazio |
| 422 | `erro_desconhecido` | parâmetro inválido no histórico (ex.: `limit` fora de 1 a 500) |
| 404 | `erro_desconhecido` | diagnóstico ou rota inexistente |
| 503 | `erro_desconhecido` | modelo indisponível (o motivo está no `GET /`) |
| 500 | `erro_desconhecido` | erro inesperado; o stack trace fica só no log |

- **200 com erro:** não é falha do servidor. A requisição funcionou, a foto é que não serve.
- **Frontends:** tratam 413 e 415 pelo código HTTP. Nas outras respostas não-OK, repassam o
  `tipo` do corpo.
- **CORS:** todas as respostas, inclusive 4xx e 5xx, saem com `Access-Control-Allow-Origin`. As
  rotas capturam os próprios erros inesperados porque, no Starlette, o handler global de
  `Exception` roda fora do `CORSMiddleware`. Por ele, o 500 sairia sem o cabeçalho, e o
  navegador mostraria "falha de rede". O handler global fica só como último recurso.
- **Log:** nem a imagem nem o nome do arquivo vão para o log.

## Histórico (RF05)
- **O que entra:** só diagnósticos com `status` "sucesso", com uma linha por folha, inclusive as
  saudáveis (`categoria` "saudavel"). Os erros não entram, e a foto não é guardada.
- **Onde:** `coffea.db`, na raiz deste repositório (`COFFEA_DB`), fora do git. As tabelas são
  criadas na subida, sem Alembic.
- **Falha na gravação:** a transação é desfeita (tudo ou nada), o erro vai para o log, e o
  diagnóstico é devolvido mesmo assim. Os frontends também guardam o próprio histórico.

**Schema.** `diagnosticos`:

| coluna | tipo | |
|---|---|---|
| `id` | INTEGER | chave primária |
| `criado_em` | DATETIME | UTC, sem fuso |

`folhas_diagnosticadas`:

| coluna | tipo | |
|---|---|---|
| `id` | INTEGER | chave primária |
| `diagnostico_id` | INTEGER | FK para `diagnosticos.id`, `ON DELETE CASCADE`, indexada |
| `folha_id` | VARCHAR | o `id` do contrato, ex.: "folha-1" |
| `categoria` | VARCHAR | código do contrato, ex.: "ferrugem" |
| `severidade` | VARCHAR | código do contrato, ex.: "baixa" |
| `regiao_x`, `regiao_y`, `regiao_raio` | FLOAT | nulos permitidos |

- **Unicidade:** `UNIQUE (diagnostico_id, folha_id)`, e não por categoria: uma foto pode ter
  várias folhas com ferrugem.
- **Chaves estrangeiras:** o `PRAGMA foreign_keys` é ligado em cada conexão do engine do
  backend.
- **Mudança de schema:** não há migração. Se o `coffea.db` existente tiver tabelas incompatíveis,
  o servidor não sobe e pede: "apague o coffea.db e suba de novo". Atualize esta seção no mesmo
  commit da mudança.

**Formato das rotas** (`GET /diagnosticos/{id}`; o `GET /diagnosticos` devolve uma lista deles):

```json
{"id": 7, "criadoEm": "2026-10-14T15:02:11Z",
 "folhas": [{"id": "folha-1", "categoria": "ferrugem", "severidade": "baixa",
             "regiao": {"x": 0.412, "y": 0.377, "raio": 0.142}}]}
```

- **Ordem:** dos mais recentes para os mais antigos; no empate, o maior `id` primeiro.
- **`criadoEm`:** em UTC, com "Z".
- **`regiao`:** só aparece se estiver gravada.

## Testes
```powershell
pip install -r requirements-dev.txt
python -m pytest                        # tudo
python -m pytest -m "not modelo_real"   # só a suíte que roda sem os pesos
```

- **Suíte padrão:** roda sem os pesos. O modelo é um falso, o banco é SQLite em memória, e as
  imagens são geradas com o Pillow nos próprios testes.
- **`modelo_real`:** usa os pesos reais e é pulada quando eles não estão na máquina. Confere que
  a resposta do POST é idêntica à de `inferencia.diagnosticar_arquivo` nas 3 primeiras fotos, em
  ordem alfabética, do BRACOT de treino (lidas do coffea-ml, sem cópia para cá). Também confere
  que uma foto sem folha dá um erro tipado do modelo.
- **Conjuntos de teste fechados:** nunca use os do coffea-ml (o BRACOL de teste, a pasta `test/`
  do BRACOT e os 115 recortes de campo de teste).

## Medição do RNF02 (≤ 5 s)
O `scripts/medir_tempo.py` mede de ponta a ponta, com o servidor real. Ele sobe o servidor com o
histórico num banco temporário e mede a subida e o `POST /diagnostico` de cada foto. Só mede tempo
e código HTTP: não olha categorias nem acertos. Ele recusa caminhos e arquivos dos conjuntos de
teste fechados.

```powershell
python scripts/medir_tempo.py --pasta ../coffea-ml/data/raw/bracot/bracot-data/train --amostra 30
```

Medição de 16/10/2026: as 30 primeiras fotos, em ordem alfabética, do BRACOT de treino (4032 ×
3024). CPU, Windows 11, 16 CPUs lógicas, Python 3.13.14, uma rodada.

| medida | segundos |
|---|---:|
| subida do servidor (até `carregado=true`) | 6,87 |
| 1ª chamada | 1,49 |
| mediana das outras 29 | 0,85 |
| p95 das outras 29 | 1,16 |
| máximo das outras 29 | 1,28 |

Todas as 30 chamadas deram HTTP 200, e nenhuma passou de 5 s. Como referência, só o modelo, no
coffea-ml, teve mediana de 0,80 s e pior caso estimado de 2,15 s.

## Dependências
- **Lista à mão:** o `requirements.txt` é uma lista fixa, mantida à mão, e **não** sai de `pip
  freeze`. É uma exceção à regra da seção "Contribuindo". O ultralytics precisa de `pip install
  --no-deps`, e um freeze o listaria como dependência normal. Uma instalação a partir dessa lista
  traria então o `opencv-python` por cima do `opencv-python-headless` (os dois gravam o mesmo
  módulo `cv2`).
- **Dependência nova:** acrescente a linha à mão, com a versão. As da inferência seguem o
  `coffea-ml/requirements.txt`. As dependências que o ultralytics pede e o resto não traz
  (`polars`, `polars-runtime-32`, `nvidia-ml-py`, `ultralytics-thop`, `ultralytics-platform`) já
  estão na lista. O `opencv-python` nunca entra, só o headless.
- **`pip check`:** acusa que o ultralytics pede `opencv-python`, `matplotlib`, `psutil` e
  `requests`. É esperado: o headless atende o ultralytics, e os outros três não são importados
  pela cadeia de inferência (conferido num venv limpo em 16/10/2026).
- **Linux:** o torch do PyPI vem com CUDA, um download grande. O ambiente de produção fica para a
  Frente 10.

## Pendências da Frente 10
- **Pesos em produção:** hoje eles vêm do clone local do coffea-ml.
- **CORS restrito:** hoje é `allow_origins=["*"]` (TODO em `app/main.py`).
- **Licença (a conferir):** o ultralytics e os pesos YOLO são AGPL-3.0, licença aceita pelo
  gestor em 10/10/2026. A AGPL tem obrigações para software oferecido como serviço em rede, e o
  repositório é público. Falta conferir o que isso exige do deploy.
- **Limite do upload no servidor:** o Starlette recebe o upload inteiro antes da rota, que só lê
  até 10 MB + 1 byte. O limite na recepção (proxy ou servidor) fica para o deploy.

## Contribuindo
Uma branch por tarefa, commits no imperativo, PR obrigatório antes de
merge na `main`. Sempre rode `pip freeze > requirements.txt` antes de
commitar uma dependência nova.
