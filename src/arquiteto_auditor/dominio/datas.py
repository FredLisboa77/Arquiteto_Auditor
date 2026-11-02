"""Leitura de datas em documentos brasileiros ("21 de março de 2010", "21/03/2010").

Tolerante às sujeiras comuns de OCR em volta da data (aspas, ponto depois de "de"). Data
impossível (30 de fevereiro) não é lida: na dúvida, não afirmar.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
          "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}

_POR_EXTENSO = re.compile(
    r"(?<!\d)(?P<dia>\d{1,2})\s*[º°o]?\s+de\s*\.?\s+(?P<mes>[a-zç]+)\s*\.?\s+de\s*\.?\s+"
    r"(?P<ano>\d{4})(?!\d)")
_NUMERICA = re.compile(r"(?<!\d)(?P<dia>\d{1,2})[/.-](?P<mes>\d{1,2})[/.-](?P<ano>\d{4})(?!\d)")


def _sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _montar(dia: str, mes: int | None, ano: str) -> date | None:
    if mes is None:
        return None
    try:
        return date(int(ano), mes, int(dia))
    except ValueError:  # data impossível
        return None


def encontrar_data(texto: str) -> tuple[date, int, int] | None:
    """A primeira data válida do texto, com o início e o fim do trecho."""
    normalizado = _sem_acentos(texto)  # mesmo tamanho do original (só tira acentos)
    candidatos = []
    for m in _POR_EXTENSO.finditer(normalizado):
        candidatos.append((m.start(), m.end(), _montar(m["dia"], _MESES.get(m["mes"]),
                                                       m["ano"])))
    for m in _NUMERICA.finditer(normalizado):
        mes = int(m["mes"])
        candidatos.append((m.start(), m.end(),
                           _montar(m["dia"], mes if 1 <= mes <= 12 else None, m["ano"])))
    validos = sorted((inicio, fim, d) for inicio, fim, d in candidatos if d is not None)
    if not validos:
        return None
    inicio, fim, data = validos[0]
    return data, inicio, fim


def ler_data(texto: str) -> date | None:
    achado = encontrar_data(texto)
    return achado[0] if achado else None
