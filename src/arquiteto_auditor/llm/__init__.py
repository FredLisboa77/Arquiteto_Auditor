"""LLM local: adaptador do Ollama, prompts versionados e conferência das citações.

O LLM só interpreta texto e cita; nunca calcula, compara ou decide (CLAUDE.md §3).
"""

from pathlib import Path

PASTA_PROMPTS = Path(__file__).parent / "prompts"


def carregar_prompt(nome: str) -> str:
    """Texto do prompt versionado em llm/prompts/<nome>.txt."""
    return (PASTA_PROMPTS / f"{nome}.txt").read_text(encoding="utf-8").strip()
