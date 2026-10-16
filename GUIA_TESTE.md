# Guia de teste pelo Swagger

Roteiro manual do coffea-backend com o modelo real. Os testes automáticos estão no README
(seção "Testes").

## Preparação
1. Suba o servidor: `fastapi dev app/main.py --host 0.0.0.0` (instalação no README).
2. Abra http://127.0.0.1:8000/docs. Em cada rota, use **Try it out** e depois **Execute**.
3. Fotos: use fotos suas ou de validação/treino. **Nunca** use os conjuntos de teste fechados do
   coffea-ml (o BRACOL de teste, a pasta `test/` do BRACOT e os recortes de campo de teste).

## Roteiro

| # | rota e entrada | saída esperada |
|---|---|---|
| 1 | `GET /` | 200, `"status": "ok"`, `"mensagem": "coffea-backend no ar"` e `modelo.carregado` = `true`, `pesos_verificados` = `true`, `motivo` = `null` |
| 2 | `POST /diagnostico`, foto boa (planta, galho ou folha de café, JPG ou PNG) | 200, `"status": "sucesso"` e `folhas` com `id`, `categoria`, `severidade` e `regiao` (mais os extras do modelo). Pode vir também um 200 com `"status": "erro"`: é o modelo dizendo que a foto não deu diagnóstico confiável |
| 3 | `POST /diagnostico`, foto ruim (parede, céu, foto escura) | 200, `"status": "erro"`, `tipo` `planta_nao_identificada` (ou `baixa_confianca`) e a mensagem do modelo em português |
| 4 | `POST /diagnostico`, formato errado (GIF, WebP, PDF, ou um texto renomeado para `.jpg`) | 415, `{"status": "erro", "tipo": "formato_invalido", "mensagem": "Formato não aceito. Envie uma foto em JPG ou PNG."}` |
| 5 | `POST /diagnostico`, arquivo acima de 10 MB (veja abaixo) | 413, `tipo` `arquivo_muito_grande` |
| 6 | `POST /diagnostico`, sem escolher arquivo | 422, `tipo` `formato_invalido`, mensagem `Envie a foto no campo "imagem", em JPG ou PNG.` |
| 7 | `GET /diagnosticos` | 200, lista com o diagnóstico do passo 2 (só os de sucesso entram), o mais recente primeiro: `id`, `criadoEm` em UTC terminando em `Z` e as `folhas` com `id`, `categoria`, `severidade` e `regiao`, sem os extras. Os passos 3 a 6 não aparecem |
| 8 | `GET /diagnosticos/{id}` com o `id` do passo 7 | 200, o mesmo diagnóstico |
| 9 | `GET /diagnosticos/{id}` com `99999` | 404, `{"status": "erro", "tipo": "erro_desconhecido", "mensagem": "Diagnóstico não encontrado."}` |
| 10 | `GET /diagnosticos` com `limit` = `0` (ou `501`) | 422, `tipo` `erro_desconhecido`, mensagem `Parâmetro inválido: limit.` |

**Arquivo de mais de 10 MB para o passo 5** (PowerShell; cria um arquivo de 11 MB cheio de zeros):

```powershell
$f = [IO.File]::Create("$PWD\grande.jpg"); $f.SetLength(11MB); $f.Close()
```

Apague o `grande.jpg` depois.

## Sem o modelo
Suba com `$env:COFFEA_CARREGAR_MODELO = "0"` antes do `fastapi dev`. O `GET /` mostra
`carregado` = `false` e `motivo` = `modelo desligado (COFFEA_CARREGAR_MODELO=0)`. O passo 2 dá
503, com `tipo` `erro_desconhecido`, e o histórico continua respondendo.
