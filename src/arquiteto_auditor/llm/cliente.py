"""Adaptador do LLM local (Ollama em 127.0.0.1): o resto do código só fala com esta classe.

Trocar de modelo ou de servidor = mudar a configuração ([llm] no config.local.toml).
Usa só a biblioteca padrão (urllib): nenhuma dependência a mais para o executável.

Toda resposta é JSON validado pelo esquema pedido (o Ollama força o formato) e com
temperatura 0 e semente fixa, para a mesma pergunta dar a mesma resposta. Por isso as
respostas podem ficar num cache em disco (pasta de dados, nunca no Git): repetir a análise
do mesmo documento não chama o modelo de novo.
O conteúdo dos documentos nunca vai para o log (CLAUDE.md §2).
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from arquiteto_auditor.config import ConfigLLM, config_llm, exigir_endereco_local

log = logging.getLogger(__name__)

SEMENTE = 1


class LLMIndisponivel(RuntimeError):
    """O Ollama não respondeu (desligado, modelo não baixado, tempo esgotado)."""


class RespostaInvalida(RuntimeError):
    """O LLM respondeu algo que não é o JSON pedido."""


class ClienteLLM:
    def __init__(self, config: ConfigLLM | None = None, pasta_cache: Path | None = None):
        self.config = config or config_llm()
        exigir_endereco_local(self.config.endereco)
        self.pasta_cache = pasta_cache
        self.chamadas = 0  # perguntas que foram mesmo ao modelo (fora do cache)

    def _chamar(self, caminho: str, corpo: dict | None, tempo_limite: float) -> dict:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        pedido = urllib.request.Request(self.config.endereco + caminho, data=dados,
                                        headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=tempo_limite) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as erro:
            raise LLMIndisponivel(f"Ollama não respondeu em {self.config.endereco}: "
                                  f"{type(erro).__name__}") from erro

    def disponivel(self) -> bool:
        """O servidor responde e o modelo configurado está baixado."""
        try:
            modelos = self._chamar("/api/tags", None, tempo_limite=5).get("models", [])
        except LLMIndisponivel:
            return False
        return any(m.get("name") == self.config.modelo for m in modelos)

    def pedir_json(self, sistema: str, usuario: str, esquema: dict) -> dict:
        """Uma pergunta, uma resposta em JSON no formato do esquema."""
        corpo = {
            "model": self.config.modelo,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": usuario}],
            "format": esquema,
            "stream": False,
            "options": {"temperature": self.config.temperatura, "seed": SEMENTE},
        }
        chave = hashlib.sha256(json.dumps(corpo, sort_keys=True).encode("utf-8")).hexdigest()
        arquivo = self.pasta_cache / f"{chave}.json" if self.pasta_cache else None
        if arquivo and arquivo.exists():
            return json.loads(arquivo.read_text(encoding="utf-8"))
        resposta = self._chamar("/api/chat", corpo, self.config.tempo_limite)
        self.chamadas += 1
        conteudo = resposta.get("message", {}).get("content", "")
        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError as erro:
            raise RespostaInvalida("o LLM não devolveu JSON") from erro
        if not isinstance(dados, dict):
            raise RespostaInvalida("o LLM não devolveu um objeto JSON")
        log.debug("LLM respondeu em %.1f s", resposta.get("total_duration", 0) / 1e9)
        if arquivo:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return dados
