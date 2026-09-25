# Guia de teste — Persistência de histórico (RF05)

Passo a passo para testar em aula/apresentação a funcionalidade de
histórico de diagnósticos (Frente 7 — Banco de Dados), integrada ao
tratamento de erros da rota `/diagnostico`.

## 1. Preparar o ambiente

Banco limpo, para começar a demo do zero:

```bash
rm -f coffea.db
```

Instalar dependências (se ainda não tiver feito):

```bash
python -m venv venv
source venv/bin/activate   # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Subir o servidor

```bash
fastapi dev app/main.py --host 0.0.0.0
```

Deixe rodando. Abra no navegador:

```
http://127.0.0.1:8000/docs
```

Essa tela (Swagger UI) é a mais fácil de usar durante a apresentação —
dá pra testar tudo clicando, sem digitar comando na frente da turma.

## 3. Roteiro de teste — via Swagger UI

1. **`GET /historico`** → "Try it out" → "Execute".
   Resultado esperado: lista vazia `[]`.
   *(mostra que ainda não gravamos nada)*

2. **`POST /diagnostico`** → "Try it out" → escolha um arquivo de imagem
   (qualquer foto de folha) → "Execute".
   Resultado esperado: `{"categoria": "Ferrugem", "severidade": "Baixa"}`

3. **`GET /historico`** de novo.
   Resultado esperado: aparece 1 registro, com `id`, `categoria`,
   `severidade` e `criado_em` (timestamp real).
   *(prova que o diagnóstico foi persistido)*

4. Repita o passo 2 mais 1 ou 2 vezes com imagens diferentes, depois
   rode `GET /historico` de novo.
   Resultado esperado: lista crescendo, ordenada do mais recente para
   o mais antigo.

5. **Prova de persistência real (não é só memória):**
   - Pare o servidor (`Ctrl+C`)
   - Suba de novo: `fastapi dev app/main.py --host 0.0.0.0`
   - Chame `GET /historico`
   - Resultado esperado: os registros continuam lá — porque estão
     salvos no arquivo `coffea.db`, não na memória do processo.

6. **Tratamento de erro (bônus):**
   - `POST /diagnostico` enviando um arquivo que não é imagem (ex: um
     `.txt`)
   - Resultado esperado: erro `400` com
     `{"erro": {"codigo": "IMAGEM_INVALIDA", ...}}`
   - Mostra que só grava no histórico quando a validação passa.

## 4. Roteiro de teste — via terminal (alternativa/backup)

```bash
curl http://127.0.0.1:8000/historico
```

```bash
curl -X POST http://127.0.0.1:8000/diagnostico -F "imagem=@/caminho/para/foto.jpg"
```

```bash
curl http://127.0.0.1:8000/historico
```

Teste de erro (arquivo inválido):

```bash
curl -X POST http://127.0.0.1:8000/diagnostico -F "imagem=@/caminho/para/arquivo.txt"
```

## 5. Ver os dados direto no banco (opcional)

Caso queira mostrar a tabela "por dentro":

```bash
sqlite3 coffea.db "SELECT * FROM diagnosticos;"
```

## 6. Cuidados antes de apresentar

- Teste o roteiro completo pelo menos uma vez antes da aula, na mesma
  rede/Wi-Fi da sala, para garantir que `--host 0.0.0.0` está
  acessível (importante se algum celular com o app Expo for testar
  junto).
- `coffea.db` está no `.gitignore` — se clonar o repositório do zero,
  o banco nasce vazio na primeira chamada. Decida antes se quer
  começar "do zero" (bom para mostrar o fluxo completo) ou já com
  alguns registros pré-carregados (bom se o tempo da apresentação for
  curto).
