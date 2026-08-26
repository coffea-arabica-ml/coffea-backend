from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Coffea Backend")

# Libera o acesso do frontend web (Vite) e do app mobile (Expo) durante o desenvolvimento.
# TODO (Frente 10): restringir isso a domínios específicos quando formos pra produção.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def raiz():
    return {"status": "ok", "mensagem": "coffea-backend no ar"}


@app.post("/diagnostico")
async def diagnosticar(imagem: UploadFile = File(...)):
    # TODO (Frente 9): substituir isso pela inferência real do modelo treinado no coffea-ml.
    return {
        "categoria": "Ferrugem",
        "severidade": "Baixa",
    }