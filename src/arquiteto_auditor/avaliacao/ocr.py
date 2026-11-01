"""Taxa de erro de caracteres (CER) do OCR, comparando com o texto correto (verdade).

CER = (inserções + exclusões + substituições) ÷ nº de caracteres da verdade.
Antes de comparar, os espaços são normalizados (vários espaços e quebras de linha viram um
espaço só): a diagramação não conta como erro, só os caracteres.
"""

from __future__ import annotations

import difflib


def normalizar_espacos(texto: str) -> str:
    return " ".join(texto.split())


def distancia_edicao(a: str, b: str) -> int:
    """Distância de Levenshtein (programação dinâmica, memória proporcional a len(b))."""
    if len(a) < len(b):
        a, b = b, a
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def cer(lido: str, verdade: str) -> float:
    verdade, lido = normalizar_espacos(verdade), normalizar_espacos(lido)
    if not verdade:
        return 0.0 if not lido else 1.0
    return distancia_edicao(lido, verdade) / len(verdade)


def separar_erros(lido: str, verdade: str) -> tuple[int, int]:
    """(erros no texto verdadeiro, caracteres a mais) entre o lido e a verdade.

    A verdade não inclui carimbos, selos, rubricas nem a marca "CÓPIA" (gerador da base
    sintética), mas eles estão impressos na imagem e o OCR os lê. Separar os dois números
    mostra se o OCR errou o texto do documento (trocou ou perdeu caracteres) ou só leu
    coisas a mais. Alinhamento pelo difflib: aproximado, mas suficiente para um relatório.
    """
    verdade, lido = normalizar_espacos(verdade), normalizar_espacos(lido)
    erros = a_mais = 0
    alinhamento = difflib.SequenceMatcher(None, verdade, lido, autojunk=False)
    for operacao, i1, i2, j1, j2 in alinhamento.get_opcodes():
        if operacao in ("replace", "delete"):
            erros += i2 - i1
        if operacao in ("replace", "insert"):
            a_mais += max(0, (j2 - j1) - (i2 - i1 if operacao == "replace" else 0))
    return erros, a_mais
