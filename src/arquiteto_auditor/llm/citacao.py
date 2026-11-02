"""Conferência da citação devolvida pelo LLM (anti-alucinação, CLAUDE.md §3 princípio 4).

1. A citação precisa existir no texto-fonte. Tolerâncias: maiúsculas/minúsculas, acentos,
   espaços e quebras de linha, aspas tipográficas e palavra hifenizada na quebra de linha
   ("lo- te" = "lote"). Fora disso, a citação é rejeitada: o LLM pode ter "melhorado" o texto.
2. O número precisa estar na citação e é RELIDO dela pelo normalizador único: o valor que
   o LLM escreveu só serve para escolher qual número da citação é o certo.
Falhou qualquer passo → None (quem chama descarta ou deixa pendente).
"""

from __future__ import annotations

import math

from arquiteto_auditor.dominio.numeros import ValorLido, encontrar_valores
from arquiteto_auditor.extracao.texto_corrido import normalizar

TAMANHO_MINIMO = 12  # uma citação de "5,00 m" sozinha não prova nada
_ASPAS = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "´": "'"})


def _compactar(texto: str) -> tuple[str, list[int]]:
    """Texto comparável e, para cada caractere dele, a posição no texto original."""
    saida: list[str] = []
    mapa: list[int] = []
    normal = normalizar(texto.translate(_ASPAS))
    i = 0
    while i < len(normal):
        c = normal[i]
        if c.isspace():
            if saida and saida[-1] != " ":
                saida.append(" ")
                mapa.append(i)
            i += 1
            continue
        if c == "-" and saida and saida[-1].isalpha():
            # hífen de quebra de linha: "LO- TE" → "LOTE" (só se seguido de espaço e letra)
            j = i + 1
            while j < len(normal) and normal[j].isspace():
                j += 1
            if j > i + 1 and j < len(normal) and normal[j].isalpha() and texto[j].islower():
                i = j
                continue
        saida.append(c)
        mapa.append(i)
        i += 1
    return "".join(saida), mapa


def localizar_citacao(citacao: str | None, texto: str) -> tuple[int, int] | None:
    """Posição (início, fim) da citação no texto, ou None se ela não está lá."""
    if not citacao:
        return None
    alvo, _ = _compactar(citacao)
    alvo = alvo.strip(" \"'")
    if len(alvo) < TAMANHO_MINIMO:
        return None
    compacto, mapa = _compactar(texto)
    posicao = compacto.find(alvo)
    if posicao < 0:
        return None
    return mapa[posicao], mapa[posicao + len(alvo) - 1] + 1


def _mesmo_numero(lido: ValorLido, valor: float) -> bool:
    if math.isclose(lido.valor, valor, abs_tol=1e-6):
        return True
    # "80 cm" é relido como 0,80 m; o LLM pode ter respondido 80.
    return "cm" in lido.texto.lower() and math.isclose(lido.valor * 100, valor, abs_tol=1e-6)


def reler_valor(citacao: str, valor_do_llm: float | None) -> ValorLido | None:
    """O número da citação que corresponde ao valor do LLM, relido pelo código."""
    if valor_do_llm is None or not math.isfinite(valor_do_llm):
        return None
    for lido in encontrar_valores(citacao):
        if _mesmo_numero(lido, valor_do_llm):
            return lido
    return None
