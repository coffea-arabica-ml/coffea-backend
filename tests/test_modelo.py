"""
Configuração, conferência dos pesos e carregamento do modelo, sem os pesos reais: um coffea-ml
falso em tmp_path, com manifesto, pesos de mentira e um inferencia.py que não importa o torch.
"""
import hashlib
import logging
import os
import sys
import textwrap
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from apoio import ORIGEM, config_de_teste, enviar, imagem
from app.config import RAIZ_REPO, Config, carregar_config
from app.main import criar_app
from app.modelo import (MANIFESTO, PASTA_CLASSIFICADOR_PADRAO, PESOS_DETECTOR_PADRAO, ErroDoModelo,
                        carregar, ler_manifesto, nome_do_detector, para_json, verificar_pesos)

CLASSIFICADOR = b"c" * 1500  # 1.500 bytes: exercita o ponto de milhar do manifesto
DETECTOR = b"detector"
INFERENCIA_FALSA = '''
CHAMADAS = []


class Modelos:
    def __init__(self, pasta, pesos, dispositivo):
        self.pasta, self.pesos, self.dispositivo = pasta, pesos, dispositivo


def carregar_modelos(pasta_do_classificador, pesos_do_detector, dispositivo="cpu"):
    CHAMADAS.append(("carregar_modelos", pasta_do_classificador, pesos_do_detector, dispositivo))
    return Modelos(pasta_do_classificador, pesos_do_detector, dispositivo)


def diagnosticar_arquivo(entrada, config=None, modelos=None):
    CHAMADAS.append(("diagnosticar_arquivo", len(entrada), config, modelos))
    return {"status": "erro", "tipo": "planta_nao_identificada", "mensagem": "sem folhas"}
'''


def sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def criar_coffea_ml(raiz, inferencia: str = INFERENCIA_FALSA, manifesto_extra: str = ""):
    """Um coffea-ml falso: model/inferencia.py, os dois pesos e o MANIFESTO.md no formato real."""
    (raiz / PASTA_CLASSIFICADOR_PADRAO).mkdir(parents=True)
    (raiz / PESOS_DETECTOR_PADRAO).parent.mkdir(parents=True)
    (raiz / PASTA_CLASSIFICADOR_PADRAO / "melhor.pt").write_bytes(CLASSIFICADOR)
    (raiz / PESOS_DETECTOR_PADRAO).write_bytes(DETECTOR)
    (raiz / "model" / "inferencia.py").write_text(inferencia, encoding="utf-8")
    (raiz / MANIFESTO).parent.mkdir(parents=True)
    (raiz / MANIFESTO).write_text(textwrap.dedent(f"""\
        # Pesos finais da cadeia

        | arquivo | bytes | SHA-256 | o que é |
        |---|---:|---|---|
        | `{PASTA_CLASSIFICADOR_PADRAO.as_posix()}/melhor.pt` | 1.500 | `{sha(CLASSIFICADOR)}` | classificador |
        | `{PESOS_DETECTOR_PADRAO.as_posix()}` | {len(DETECTOR)} | `{sha(DETECTOR)}` | detector |

        ## Arquivos que não são pesos da cadeia

        - `model/runs/detector_base/weights/best.pt` (8 bytes, SHA-256
          `{sha(b"outro")}`): a época de melhor métrica.
        {manifesto_extra}"""), encoding="utf-8")
    return raiz


@pytest.fixture
def isolar_imports(monkeypatch):
    """carregar() mexe no sys.path e importa um "inferencia": desfaz os dois no fim do teste, para
    o falso não vazar para os testes com o modelo real."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    anterior = sys.modules.pop("inferencia", None)
    yield
    sys.modules.pop("inferencia", None)
    if anterior is not None:
        sys.modules["inferencia"] = anterior


@pytest.fixture
def coffea_ml(tmp_path, isolar_imports):
    return criar_coffea_ml(tmp_path / "coffea-ml")


def config_do(coffea_ml, **mudancas) -> Config:
    return replace(config_de_teste(coffea_ml.parent), coffea_ml_dir=coffea_ml, **mudancas)


# ----------------------------------------------------------------------------- config
def test_config_padrao():
    config = carregar_config({})
    assert config.coffea_ml_dir == (RAIZ_REPO.parent / "coffea-ml").resolve()
    assert config.coffea_ml_dir.is_absolute()
    assert (config.pasta_classificador, config.pesos_detector) == (None, None)
    assert (config.verificar_pesos, config.concorrencia, config.carregar_modelo) == (True, 1, True)
    assert config.caminho_db == RAIZ_REPO / "coffea.db"


def test_caminho_relativo_vale_a_partir_da_raiz_e_nao_do_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = carregar_config({"COFFEA_DB": "dados/historico.db", "COFFEA_ML_DIR": "../ml",
                              "COFFEA_PESOS_DETECTOR": str(tmp_path / "last.pt"),
                              "COFFEA_PASTA_CLASSIFICADOR": "  ", "COFFEA_CONCORRENCIA": "2",
                              "COFFEA_VERIFICAR_PESOS": "0", "COFFEA_CARREGAR_MODELO": "false"})
    assert config.caminho_db == RAIZ_REPO / "dados" / "historico.db"
    assert config.coffea_ml_dir == (RAIZ_REPO.parent / "ml").resolve()
    assert config.pesos_detector == tmp_path.resolve() / "last.pt"
    assert config.pasta_classificador is None  # em branco conta como ausente
    assert (config.concorrencia, config.verificar_pesos, config.carregar_modelo) == (2, False, False)


@pytest.mark.parametrize("nome, valor", [("COFFEA_VERIFICAR_PESOS", "talvez"),
                                         ("COFFEA_CARREGAR_MODELO", "2"),
                                         ("COFFEA_CONCORRENCIA", "0"),
                                         ("COFFEA_CONCORRENCIA", "dois")])
def test_valor_invalido_impede_a_subida(nome, valor):
    with pytest.raises(ValueError, match=nome):
        carregar_config({nome: valor})


def test_env_da_raiz_e_lido_sem_sobrescrever_o_ambiente(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("COFFEA_CONCORRENCIA=3\nCOFFEA_DB=do-env.db\n", encoding="utf-8")
    monkeypatch.setattr("app.config.RAIZ_REPO", tmp_path)
    monkeypatch.setattr(os, "environ", {"COFFEA_DB": "do-ambiente.db"})
    config = carregar_config()
    assert config.concorrencia == 3
    assert config.caminho_db == tmp_path.resolve() / "do-ambiente.db"


# -------------------------------------------------------------------------- manifesto
def test_le_o_manifesto_real_do_coffea_ml():
    caminho = carregar_config({}).coffea_ml_dir / MANIFESTO
    if not caminho.is_file():
        pytest.skip("coffea-ml não está na máquina")
    entradas = {e.arquivo: e for e in ler_manifesto(caminho)}
    assert {f"{PASTA_CLASSIFICADOR_PADRAO.as_posix()}/melhor.pt",
            PESOS_DETECTOR_PADRAO.as_posix()} <= set(entradas)
    assert all(len(e.sha256) == 64 and e.tamanho > 0 for e in entradas.values())
    assert not any(a.endswith("best.pt") for a in entradas)  # fora da tabela


def test_le_bytes_com_ponto_de_milhar_e_ignora_a_lista(coffea_ml):
    entradas = ler_manifesto(coffea_ml / MANIFESTO)
    assert [(e.arquivo, e.tamanho) for e in entradas] == [
        (f"{PASTA_CLASSIFICADOR_PADRAO.as_posix()}/melhor.pt", 1500),
        (PESOS_DETECTOR_PADRAO.as_posix(), len(DETECTOR))]


def test_manifesto_ausente_ou_sem_tabela(tmp_path):
    with pytest.raises(ErroDoModelo, match="não encontrado"):
        ler_manifesto(tmp_path / "MANIFESTO.md")
    (tmp_path / "MANIFESTO.md").write_text("# sem tabela\n", encoding="utf-8")
    with pytest.raises(ErroDoModelo, match="sem a tabela"):
        ler_manifesto(tmp_path / "MANIFESTO.md")


# ------------------------------------------------------------------------------ pesos
def pesos_padrao(coffea_ml):
    return [coffea_ml / PASTA_CLASSIFICADOR_PADRAO / "melhor.pt", coffea_ml / PESOS_DETECTOR_PADRAO]


def test_pesos_que_conferem(coffea_ml):
    verificar_pesos(pesos_padrao(coffea_ml), coffea_ml)


def test_tamanho_diferente(coffea_ml):
    (coffea_ml / PESOS_DETECTOR_PADRAO).write_bytes(DETECTOR + b"x")
    with pytest.raises(ErroDoModelo, match=r"last\.pt não confere com o MANIFESTO\.md \(tamanho\)"):
        verificar_pesos(pesos_padrao(coffea_ml), coffea_ml)


def test_sha256_diferente_com_o_mesmo_tamanho(coffea_ml):
    (coffea_ml / PASTA_CLASSIFICADOR_PADRAO / "melhor.pt").write_bytes(b"d" * 1500)
    with pytest.raises(ErroDoModelo, match=r"melhor\.pt não confere com o MANIFESTO\.md \(SHA-256\)"):
        verificar_pesos(pesos_padrao(coffea_ml), coffea_ml)


def test_peso_ausente(coffea_ml):
    (coffea_ml / PESOS_DETECTOR_PADRAO).unlink()
    with pytest.raises(ErroDoModelo, match="pesos não encontrados: last.pt"):
        verificar_pesos(pesos_padrao(coffea_ml), coffea_ml)


def test_caminho_customizado_confere_pelo_nome(coffea_ml, tmp_path):
    outro = tmp_path / "pesos-copiados"
    outro.mkdir()
    (outro / "melhor.pt").write_bytes(CLASSIFICADOR)
    (outro / "last.pt").write_bytes(DETECTOR)
    verificar_pesos([outro / "melhor.pt", outro / "last.pt"], coffea_ml)
    (outro / "detector.pt").write_bytes(DETECTOR)
    with pytest.raises(ErroDoModelo, match="detector.pt não está no MANIFESTO.md"):
        verificar_pesos([outro / "detector.pt"], coffea_ml)


# --------------------------------------------------------------------------- carregar
def test_carrega_com_os_pesos_conferidos(coffea_ml):
    modelo = carregar(config_do(coffea_ml))
    assert (modelo.carregado, modelo.pesos_verificados, modelo.motivo) == (True, True, None)
    pasta, pesos = coffea_ml / PASTA_CLASSIFICADOR_PADRAO, coffea_ml / PESOS_DETECTOR_PADRAO
    assert modelo.inferencia.CHAMADAS == [("carregar_modelos", pasta, pesos, "cpu")]
    modelo.diagnosticar(b"\xff\xd8\xff")
    # só diagnosticar_arquivo, com os bytes e os modelos carregados, sem config (limiares congelados)
    assert modelo.inferencia.CHAMADAS[-1] == ("diagnosticar_arquivo", 3, None, modelo.modelos)
    assert str(coffea_ml / "model") in sys.path


def test_caminhos_customizados_vao_para_o_carregar_modelos(coffea_ml, tmp_path):
    pasta = tmp_path / "meu_run"
    pasta.mkdir()
    (pasta / "melhor.pt").write_bytes(CLASSIFICADOR)
    (tmp_path / "last.pt").write_bytes(DETECTOR)
    modelo = carregar(config_do(coffea_ml, pasta_classificador=pasta,
                                pesos_detector=tmp_path / "last.pt"))
    assert modelo.carregado and modelo.pesos_verificados
    assert modelo.inferencia.CHAMADAS[0] == ("carregar_modelos", pasta, tmp_path / "last.pt", "cpu")
    assert (modelo.classificador, modelo.detector) == ("meu_run", "last.pt")


def test_sem_conferencia_carrega_mas_nao_marca_verificado(coffea_ml):
    (coffea_ml / PESOS_DETECTOR_PADRAO).write_bytes(b"outro")
    modelo = carregar(config_do(coffea_ml, verificar_pesos=False))
    assert (modelo.carregado, modelo.pesos_verificados) == (True, False)


def test_pesos_que_nao_conferem_deixam_o_modelo_indisponivel(coffea_ml, caplog):
    (coffea_ml / PESOS_DETECTOR_PADRAO).write_bytes(b"x" * len(DETECTOR))
    with caplog.at_level(logging.ERROR, logger="coffea"):
        modelo = carregar(config_do(coffea_ml))
    assert (modelo.carregado, modelo.pesos_verificados) == (False, False)
    assert modelo.motivo == "last.pt não confere com o MANIFESTO.md (SHA-256)"
    assert "inferencia" not in sys.modules  # nem chegou a importar
    assert "Modelo indisponível" in caplog.text


def test_falha_no_carregamento_vai_para_o_log(tmp_path, isolar_imports, caplog):
    coffea_ml = criar_coffea_ml(tmp_path / "coffea-ml", inferencia=INFERENCIA_FALSA.replace(
        "    CHAMADAS.append((\"carregar_modelos\"", "    raise MemoryError('sem memória')\n"
        "    CHAMADAS.append((\"carregar_modelos\""))
    with caplog.at_level(logging.ERROR, logger="coffea"):
        modelo = carregar(config_do(coffea_ml))
    assert (modelo.carregado, modelo.pesos_verificados) == (False, True)
    assert modelo.motivo == "falha ao carregar o modelo (ver o log do servidor)"
    assert "Traceback" in caplog.text and "sem memória" in caplog.text


def test_import_quebrado_nao_derruba(tmp_path, isolar_imports):
    coffea_ml = criar_coffea_ml(tmp_path / "coffea-ml", inferencia="import modulo_que_nao_existe\n")
    modelo = carregar(config_do(coffea_ml))
    assert not modelo.carregado
    assert modelo.motivo == "falha ao carregar o modelo (ver o log do servidor)"


def test_conflito_de_nomes_com_o_pacote_app(coffea_ml):
    (coffea_ml / "model" / "app.py").write_text("", encoding="utf-8")
    modelo = carregar(config_do(coffea_ml))
    assert not modelo.carregado
    assert modelo.motivo == "conflito de nomes: o coffea-ml tem um módulo app"


def test_coffea_ml_ausente(tmp_path, isolar_imports):
    modelo = carregar(config_do(tmp_path / "nao-existe"))
    assert not modelo.carregado
    assert modelo.motivo == "coffea-ml não encontrado (confira o COFFEA_ML_DIR)"


def test_modelo_desligado_nem_importa(coffea_ml):
    modelo = carregar(config_do(coffea_ml, carregar_modelo=False))
    assert not modelo.carregado
    assert modelo.motivo == "modelo desligado (COFFEA_CARREGAR_MODELO=0)"
    assert "inferencia" not in sys.modules
    with pytest.raises(RuntimeError):
        modelo.diagnosticar(b"\xff\xd8\xff")


def test_nome_do_detector():
    assert nome_do_detector(PESOS_DETECTOR_PADRAO) == "detector_base"
    assert nome_do_detector(PESOS_DETECTOR_PADRAO.parent.parent / "last.pt") == "last.pt"


# --------------------------------------------------------------------------- servidor
def test_servidor_sobe_com_o_modelo_indisponivel(coffea_ml):
    (coffea_ml / PESOS_DETECTOR_PADRAO).write_bytes(b"x" * len(DETECTOR))
    with TestClient(criar_app(config_do(coffea_ml)), headers={"Origin": ORIGEM}) as cliente:
        raiz = cliente.get("/")
        assert raiz.status_code == 200
        assert raiz.json()["modelo"] == {
            "carregado": False, "classificador": "base_resnet50_bracol",
            "detector": "detector_base", "pesos_verificados": False,
            "motivo": "last.pt não confere com o MANIFESTO.md (SHA-256)"}
        assert str(coffea_ml.parent.name) not in raiz.text and "\\\\" not in raiz.text
        resposta = enviar(cliente, imagem())
        assert resposta.status_code == 503
        assert resposta.headers.get("access-control-allow-origin") in ("*", ORIGEM)


def test_servidor_com_o_modelo_carregado_chama_o_inferencia(coffea_ml):
    with TestClient(criar_app(config_do(coffea_ml))) as cliente:
        assert cliente.get("/").json()["modelo"]["carregado"] is True
        resposta = enviar(cliente, imagem())
        assert resposta.status_code == 200
        assert resposta.json() == {"status": "erro", "tipo": "planta_nao_identificada",
                                   "mensagem": "sem folhas"}


def test_raiz_mantem_o_esqueleto_e_acrescenta_o_modelo(cliente):
    corpo = cliente.get("/").json()
    assert (corpo["status"], corpo["mensagem"]) == ("ok", "coffea-backend no ar")
    assert set(corpo["modelo"]) == {"carregado", "classificador", "detector",
                                    "pesos_verificados", "motivo"}


# ------------------------------------------------------------------------------- JSON
def test_para_json_converte_numpy_sem_mudar_o_valor():
    bruto = {"a": np.float32(0.5), "b": np.int64(7), "c": np.bool_(True),
             "d": (1, np.array([0.25, 1.0])), "e": [None, "x", 1.5]}
    convertido = para_json(bruto)
    assert convertido == {"a": 0.5, "b": 7, "c": True, "d": [1, [0.25, 1.0]], "e": [None, "x", 1.5]}
    assert type(convertido["a"]) is float and type(convertido["c"]) is bool


def test_para_json_nao_mexe_nos_tipos_nativos():
    from apoio import SUCESSO
    assert para_json(SUCESSO) == SUCESSO
