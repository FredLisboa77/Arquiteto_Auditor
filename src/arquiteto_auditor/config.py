"""Configuração do Arquiteto Auditor (config.local.toml, com config.exemplo.toml como padrão).

Os caminhos relativos (ex.: "modelos/tessdata") são resolvidos a partir da raiz do projeto.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

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
