"""Fonte de traço simples que imita a fonte SHX "txt" do AutoCAD.

No PDF exportado pelo AutoCAD, o texto em fonte SHX vira DESENHO (pequenos segmentos de reta),
não texto selecionável. O AutoCAD grava o texto original num comentário invisível do PDF
(calibração com exemplos reais: docs/06-calibracao-exemplos-reais.md §1).

Cada letra é desenhada numa grade de 4 x 6 unidades (altura das maiúsculas = 6). Só há
maiúsculas, como no uso típico em desenho técnico; os acentos são omitidos no desenho (o texto
completo, com acentos, fica no comentário).
"""

from __future__ import annotations

import unicodedata

ALTURA = 6.0  # altura das maiúsculas, em unidades da grade
AVANCO = 5.0  # largura de cada caractere, incluindo o espaço até o próximo

_GLIFOS = {
    "A": "0,0 2,6 4,0|0.8,2.4 3.2,2.4",
    "B": "0,0 0,6 3,6 4,5 4,4 3,3 0,3|3,3 4,2 4,1 3,0 0,0",
    "C": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1",
    "D": "0,0 0,6 2.5,6 4,4.5 4,1.5 2.5,0 0,0",
    "E": "4,6 0,6 0,0 4,0|0,3 3,3",
    "F": "4,6 0,6 0,0|0,3 3,3",
    "G": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,3 2,3",
    "H": "0,0 0,6|4,0 4,6|0,3 4,3",
    "I": "1,6 3,6|2,6 2,0|1,0 3,0",
    "J": "4,6 4,1 3,0 1,0 0,1",
    "K": "0,0 0,6|4,6 0,2|1.3,3.3 4,0",
    "L": "0,6 0,0 4,0",
    "M": "0,0 0,6 2,3 4,6 4,0",
    "N": "0,0 0,6 4,0 4,6",
    "O": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0",
    "P": "0,0 0,6 3,6 4,5 4,4 3,3 0,3",
    "Q": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0|2.5,1.5 4,0",
    "R": "0,0 0,6 3,6 4,5 4,4 3,3 0,3|2,3 4,0",
    "S": "4,5 3,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 1,0 0,1",
    "T": "0,6 4,6|2,6 2,0",
    "U": "0,6 0,1 1,0 3,0 4,1 4,6",
    "V": "0,6 2,0 4,6",
    "W": "0,6 1,0 2,4 3,0 4,6",
    "X": "0,0 4,6|0,6 4,0",
    "Y": "0,6 2,3 4,6|2,3 2,0",
    "Z": "0,6 4,6 0,0 4,0",
    "0": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0",
    "1": "1,5 2,6 2,0|1,0 3,0",
    "2": "0,5 1,6 3,6 4,5 4,4 0,0 4,0",
    "3": "0,5 1,6 3,6 4,5 4,4 3,3 1.5,3|3,3 4,2 4,1 3,0 1,0 0,1",
    "4": "3,0 3,6 0,2 4,2",
    "5": "4,6 0,6 0,3 3,3 4,2 4,1 3,0 1,0 0,1",
    "6": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,2 3,3 0,3",
    "7": "0,6 4,6 1.5,0",
    "8": "1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3",
    "9": "4,3 1,3 0,4 0,5 1,6 3,6 4,5 4,1 3,0 1,0 0,1",
    ".": "1.8,0 2.2,0 2.2,0.4 1.8,0.4 1.8,0",
    ",": "2.2,0.4 2.2,0 1.6,-1",
    ";": "2,4 2,4.5|2.2,0.4 2.2,0 1.6,-1",
    ":": "2,0.5 2,1|2,4 2,4.5",
    "-": "1,3 3,3",
    "—": "0,3 4,3",
    "_": "0,0 4,0",
    "/": "0,0 4,6",
    "(": "3,6 2,5 1.6,3 2,1 3,0",
    ")": "1,6 2,5 2.4,3 2,1 1,0",
    "=": "0.5,2 3.5,2|0.5,4 3.5,4",
    "+": "2,1 2,5|0,3 4,3",
    "%": "0,6 1,6 1,5 0,5 0,6|3,1 4,1 4,0 3,0 3,1|0,0 4,6",
    "²": "0.5,5 1,5.5 2,5.5 2.5,5 0.5,3.5 2.5,3.5",
    "³": "0.5,5.5 2.5,5.5 1.5,4.5 2.5,4 2,3.5 0.5,3.5",
    "º": "1,6 2,6 2,5 1,5 1,6",
    "°": "1,6 2,6 2,5 1,5 1,6",
    "'": "2,6 2,4.5",
    "\"": "1.5,6 1.5,4.5|2.5,6 2.5,4.5",
    "!": "2,6 2,2|2,0.4 2,0",
    "?": "0,5 1,6 3,6 4,5 4,4 2,3 2,2|2,0.4 2,0",
    "&": "4,0 0.5,4.5 1,6 2,6 2.5,5 0,2 0,1 1,0 2.5,0 4,2",
}


def _ler(definicao: str) -> list[list[tuple[float, float]]]:
    return [[tuple(float(v) for v in ponto.split(",")) for ponto in traco.split()]
            for traco in definicao.split("|")]


GLIFOS = {letra: _ler(definicao) for letra, definicao in _GLIFOS.items()}


def normalizar(texto: str) -> str:
    """Maiúsculas sem acento (Ç → C), mantendo ², ³ e º."""
    resultado = []
    for caractere in texto:
        if caractere in "²³º°":
            resultado.append(caractere)
            continue
        base = unicodedata.normalize("NFD", caractere.upper())
        resultado.append("".join(c for c in base if not unicodedata.combining(c)))
    return "".join(resultado)


def largura(texto: str) -> float:
    """Largura do texto em unidades da grade (sem o espaço depois do último caractere)."""
    return max(0.0, len(normalizar(texto)) * AVANCO - (AVANCO - 4.0))


def tracos(texto: str) -> list[list[tuple[float, float]]]:
    """Segmentos (polilinhas) do texto, na grade: x de 0 a largura(texto), y de 0 a 6.

    Caracteres sem desenho (espaço e símbolos raros) só avançam.
    """
    resultado = []
    for indice, caractere in enumerate(normalizar(texto)):
        deslocamento = indice * AVANCO
        for traco in GLIFOS.get(caractere, []):
            resultado.append([(x + deslocamento, y) for x, y in traco])
    return resultado
