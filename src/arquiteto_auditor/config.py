"""Configuração do Arquiteto Auditor (config.local.toml, com config.exemplo.toml como padrão).

Os caminhos relativos (ex.: "modelos/tessdata") são resolvidos a partir da raiz do projeto.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[2]


@cache
def carregar_config() -> dict:
    for nome in ("config.local.toml", "config.exemplo.toml"):
        caminho = RAIZ / nome
        if caminho.exists():
            return tomllib.loads(caminho.read_text(encoding="utf-8"))
    return {}


def caminho_do_projeto(valor: str) -> Path:
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else RAIZ / caminho


@dataclass(frozen=True)
class ConfigOCR:
    tesseract_cmd: str | None
    tessdata_dir: Path
    idioma: str = "por"
    dpi: int = 300  # resolução em que as páginas são lidas (imagens menores são ampliadas)


def config_ocr() -> ConfigOCR:
    ocr = carregar_config().get("ocr", {})
    comando = ocr.get("tesseract_cmd")
    if not comando or not Path(comando).exists():
        comando = shutil.which("tesseract")
    return ConfigOCR(
        tesseract_cmd=comando,
        tessdata_dir=caminho_do_projeto(ocr.get("tessdata_dir", "modelos/tessdata")),
        idioma=ocr.get("idioma", "por"),
        dpi=int(ocr.get("dpi", 300)),
    )


def limiar_confianca_ocr() -> float:
    """Abaixo desta confiança do OCR, o valor lido vai para a confirmação do revisor."""
    return float(carregar_config().get("ocr", {}).get("limiar_confianca", 0.6))


def pasta_de_dados() -> Path:
    """Onde ficam histórico, relatórios e cache (dados pessoais: nunca vão para o Git)."""
    return caminho_do_projeto(carregar_config().get("pastas", {}).get("dados", "dados_privados"))


ENDERECOS_LOCAIS = ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True)
class ConfigLLM:
    endereco: str = "http://127.0.0.1:11434"
    modelo: str = "qwen2.5:7b-instruct-q4_K_M"
    temperatura: float = 0.0
    tempo_limite: float = 300.0  # segundos; a primeira chamada carrega o modelo (~2 min)


def config_llm() -> ConfigLLM:
    """Configuração do LLM. Só aceita servidor nesta máquina: nada de documento sai dela."""
    llm = carregar_config().get("llm", {})
    padrao = ConfigLLM()
    config = ConfigLLM(
        endereco=str(llm.get("endereco", padrao.endereco)).rstrip("/"),
        modelo=str(llm.get("modelo", padrao.modelo)),
        temperatura=float(llm.get("temperatura", padrao.temperatura)),
        tempo_limite=float(llm.get("tempo_limite", padrao.tempo_limite)),
    )
    exigir_endereco_local(config.endereco)
    return config


def exigir_endereco_local(endereco: str) -> None:
    if urlparse(endereco).hostname not in ENDERECOS_LOCAIS:
        raise ValueError(f"o LLM precisa rodar nesta máquina (127.0.0.1); recebido: {endereco}")
