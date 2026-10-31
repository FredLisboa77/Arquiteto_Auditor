"""Verifica se o computador tem tudo que o Arquiteto Auditor precisa.

Uso:  .venv\\Scripts\\python scripts\\verificar_ambiente.py
Mostra ✓ (ok), ! (aviso: funciona, mas há algo a melhorar) ou ✗ (falta algo).
Lê os caminhos de config.local.toml, se existir; senão de config.exemplo.toml.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OK, AVISO, FALTA = "✓", "!", "✗"


def carregar_config() -> dict:
    for nome in ("config.local.toml", "config.exemplo.toml"):
        arquivo = RAIZ / nome
        if arquivo.exists():
            return tomllib.loads(arquivo.read_text(encoding="utf-8"))
    return {}


def checar_python() -> tuple[str, str]:
    versao = sys.version.split()[0]
    no_venv = sys.prefix != sys.base_prefix
    if sys.version_info[:2] != (3, 11):
        return FALTA, f"Python {versao} — o projeto usa 3.11 (rode com .venv\\Scripts\\python)"
    if not no_venv:
        return AVISO, f"Python {versao}, mas fora do ambiente virtual .venv"
    return OK, f"Python {versao} no ambiente virtual"


def checar_tesseract(config: dict) -> tuple[str, str]:
    ocr = config.get("ocr", {})
    comando = ocr.get("tesseract_cmd") or shutil.which("tesseract")
    if not comando or not Path(comando).exists():
        return FALTA, "Tesseract não encontrado (ver docs/03-arquitetura.md §6.2)"
    tessdata = RAIZ / ocr.get("tessdata_dir", "modelos/tessdata")
    idioma = ocr.get("idioma", "por")
    saida = subprocess.run(
        [comando, "--tessdata-dir", str(tessdata), "--list-langs"],
        capture_output=True, text=True,
    )
    idiomas = saida.stdout.split()
    versao = subprocess.run([comando, "--version"], capture_output=True, text=True)
    primeira_linha = (versao.stdout or versao.stderr).splitlines()[0]
    if idioma not in idiomas:
        return FALTA, f"{primeira_linha}, mas sem o idioma '{idioma}' em {tessdata}"
    return OK, f"{primeira_linha} com idioma '{idioma}'"


def checar_ollama(config: dict) -> tuple[str, str]:
    llm = config.get("llm", {})
    endereco = llm.get("endereco", "http://127.0.0.1:11434")
    modelo = llm.get("modelo", "")
    try:
        with urllib.request.urlopen(f"{endereco}/api/tags", timeout=5) as resposta:
            modelos = [m["name"] for m in json.load(resposta).get("models", [])]
    except OSError:
        return FALTA, f"Ollama não responde em {endereco} (abra o aplicativo Ollama)"
    if modelo not in modelos:
        return FALTA, f"Ollama ok, mas o modelo '{modelo}' não está baixado (ollama pull {modelo})"
    return OK, f"Ollama ok, modelo '{modelo}' disponível"


def checar_gpu() -> tuple[str, str]:
    if not shutil.which("nvidia-smi"):
        return AVISO, "nvidia-smi não encontrado — o LLM rodará só na CPU (lento)"
    saida = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
         "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    return OK, f"GPU: {saida.stdout.strip()}"


def checar_disco() -> tuple[str, str]:
    livre_gb = shutil.disk_usage(RAIZ).free / 1024**3
    if livre_gb < 20:
        return AVISO, f"Pouco espaço livre no disco do projeto: {livre_gb:.0f} GB"
    return OK, f"Espaço livre no disco do projeto: {livre_gb:.0f} GB"


def checar_protecao_git() -> tuple[str, str]:
    gancho = RAIZ / ".git" / "hooks" / "pre-commit"
    if not gancho.exists():
        return FALTA, "Gancho anti-vazamento não instalado (.venv\\Scripts\\pre-commit install)"
    return OK, "Gancho anti-vazamento instalado no Git"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    config = carregar_config()
    verificacoes = {
        "Python": checar_python,
        "Tesseract (OCR)": lambda: checar_tesseract(config),
        "Ollama (LLM local)": lambda: checar_ollama(config),
        "Placa de vídeo": checar_gpu,
        "Disco": checar_disco,
        "Proteção do Git": checar_protecao_git,
    }
    faltas = 0
    for nome, verificacao in verificacoes.items():
        simbolo, mensagem = verificacao()
        faltas += simbolo == FALTA
        print(f"  {simbolo} {nome:<20} {mensagem}")
    print("\nAmbiente pronto." if not faltas else f"\n{faltas} item(ns) a resolver.")
    return 1 if faltas else 0


if __name__ == "__main__":
    sys.exit(main())
