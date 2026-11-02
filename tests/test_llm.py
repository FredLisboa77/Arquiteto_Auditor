"""Testes do adaptador do LLM e da conferência de citações (Fase 8).

Os testes não precisam do Ollama: um servidor falso em 127.0.0.1 faz o papel dele.
Para testar com o Ollama de verdade: AA_TESTAR_LLM=1 pytest tests/test_llm.py
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from arquiteto_auditor.config import ConfigLLM, exigir_endereco_local
from arquiteto_auditor.llm import carregar_prompt
from arquiteto_auditor.llm.citacao import localizar_citacao, reler_valor
from arquiteto_auditor.llm.cliente import ClienteLLM, LLMIndisponivel, RespostaInvalida

# ------------------------------------------------------------------ privacidade


@pytest.mark.parametrize("endereco", ["http://127.0.0.1:11434", "http://localhost:11434"])
def test_endereco_local_aceito(endereco):
    exigir_endereco_local(endereco)


@pytest.mark.parametrize("endereco", ["http://192.168.0.10:11434", "https://api.exemplo.com",
                                      "http://127.0.0.1.exemplo.com:11434"])
def test_endereco_externo_recusado(endereco):
    with pytest.raises(ValueError, match="nesta máquina"):
        exigir_endereco_local(endereco)
    with pytest.raises(ValueError):
        ClienteLLM(ConfigLLM(endereco=endereco))


# ------------------------------------------------------------------ cliente


class _OllamaFalso(BaseHTTPRequestHandler):
    resposta = '{"valor": 5.0}'
    pedidos: list = []

    def do_GET(self):  # /api/tags
        self._enviar({"models": [{"name": "modelo-teste"}]})

    def do_POST(self):  # /api/chat
        tamanho = int(self.headers["Content-Length"])
        _OllamaFalso.pedidos.append(json.loads(self.rfile.read(tamanho)))
        self._enviar({"message": {"content": _OllamaFalso.resposta}, "total_duration": 1})

    def _enviar(self, dados):
        corpo = json.dumps(dados).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass


@pytest.fixture
def ollama_falso():
    servidor = HTTPServer(("127.0.0.1", 0), _OllamaFalso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    _OllamaFalso.pedidos = []
    yield ClienteLLM(ConfigLLM(endereco=f"http://127.0.0.1:{servidor.server_port}",
                               modelo="modelo-teste", tempo_limite=5))
    servidor.shutdown()


def test_pedir_json(ollama_falso):
    esquema = {"type": "object", "properties": {"valor": {"type": "number"}}}
    assert ollama_falso.pedir_json("sistema", "pergunta", esquema) == {"valor": 5.0}
    [pedido] = _OllamaFalso.pedidos
    assert pedido["model"] == "modelo-teste"
    assert pedido["format"] == esquema
    assert pedido["options"] == {"temperature": 0.0, "seed": 1}
    assert [m["role"] for m in pedido["messages"]] == ["system", "user"]


def test_resposta_que_nao_e_json(ollama_falso):
    _OllamaFalso.resposta = "o recuo é 5 metros"
    try:
        with pytest.raises(RespostaInvalida):
            ollama_falso.pedir_json("s", "u", {})
    finally:
        _OllamaFalso.resposta = '{"valor": 5.0}'


def test_disponivel(ollama_falso):
    assert ollama_falso.disponivel()
    outro_modelo = ClienteLLM(ConfigLLM(endereco=ollama_falso.config.endereco, modelo="outro"))
    assert not outro_modelo.disponivel()


def test_ollama_desligado():
    cliente = ClienteLLM(ConfigLLM(endereco="http://127.0.0.1:9", tempo_limite=2))
    assert not cliente.disponivel()
    with pytest.raises(LLMIndisponivel):
        cliente.pedir_json("s", "u", {})


def test_prompts_versionados():
    assert "Nunca invente" in carregar_prompt("parametro_sistema")
    assert "<<TRECHOS>>" in carregar_prompt("parametro_pedido")


# ------------------------------------------------------------------ citação

TEXTO = ("Art. 22. Na ZR-2, o recuo frontal\nmínimo será de 5,00 m. (Redação dada pela Lei nº "
         "282, de 2016)\nRedação anterior: “Na ZR-2, o recuo frontal mínimo será de 6,00 m.”\n"
         "Art. 23. O lo-\nte terá testada mínima de 10,00 m.")


def test_citacao_exata():
    citacao = "Na ZR-2, o recuo frontal mínimo será de 5,00 m."
    inicio, fim = localizar_citacao(citacao, TEXTO)
    assert TEXTO[inicio:fim] == "Na ZR-2, o recuo frontal\nmínimo será de 5,00 m."


def test_citacao_com_tolerancias():
    assert localizar_citacao("na zr-2, o RECUO frontal minimo   sera de 5,00 m", TEXTO)
    assert localizar_citacao('"Na ZR-2, o recuo frontal mínimo será de 6,00 m."', TEXTO)
    inicio, fim = localizar_citacao("O lote terá testada mínima de 10,00 m.", TEXTO)
    assert TEXTO[inicio:fim] == "O lo-\nte terá testada mínima de 10,00 m."


@pytest.mark.parametrize("citacao", [
    "Na ZR-2, o recuo frontal mínimo será de 4,00 m.",  # número trocado
    "Na ZR-2, o recuo frontal mínimo é de 5,00 m.",  # texto "melhorado"
    "Na ZR-2, o recuo frontal ... 5,00 m.",  # resumido
    "5,00 m.",  # curta demais para provar algo
    "", None,
])
def test_citacao_rejeitada(citacao):
    assert localizar_citacao(citacao, TEXTO) is None


def test_reler_valor_da_citacao():
    citacao = "a) lote mínimo: 300,00 m²; b) testada mínima: 8,00 m;"
    lido = reler_valor(citacao, 8.0)
    assert (lido.valor, lido.unidade, lido.texto) == (8.0, "m", "8,00 m")
    assert reler_valor(citacao, 7.5) is None  # o número do LLM não está na citação
    assert reler_valor(citacao, None) is None
    assert reler_valor(citacao, float("nan")) is None


def test_reler_valor_em_centimetros_e_por_extenso():
    assert reler_valor("muro de 80 cm (oitenta centímetros) de altura", 80).valor == 0.8
    assert reler_valor("muro de 80 cm (oitenta centímetros) de altura", 0.8).valor == 0.8
    assert reler_valor("no máximo 02 (dois) pavimentos", 2).valor == 2


# ------------------------------------------------------------------ Ollama de verdade


@pytest.mark.skipif(os.environ.get("AA_TESTAR_LLM") != "1", reason="defina AA_TESTAR_LLM=1")
def test_ollama_real_responde_json():
    cliente = ClienteLLM()
    assert cliente.disponivel(), "Ollama desligado ou modelo não baixado"
    esquema = {"type": "object", "properties": {"numero": {"type": ["number", "null"]}},
               "required": ["numero"]}
    resposta = cliente.pedir_json("Responda só com JSON.", "Quanto é o número 'dez'?", esquema)
    assert resposta == {"numero": 10}
