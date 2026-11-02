"""Geometria vetorial útil para a extração: as linhas de cota desenhadas numa prancha.

Uma linha de cota é um segmento horizontal ou vertical com um TRACINHO OBLÍQUO (≈ 45°) em
cada ponta — a marcação usual dos desenhos de arquitetura no Brasil. Saber onde estão as
linhas de cota permite achar a cota "só gráfica": a linha está desenhada, mas o número não
foi escrito (docs/02 §4.1, item COTA_INDEFINIDA).

Cotas com setas em vez de tracinhos ainda não são reconhecidas (limitação conhecida).
"""

from __future__ import annotations

import math

import pymupdf

TRACINHO_MIN, TRACINHO_MAX = 3.0, 20.0  # comprimento do tracinho, em pontos
INCLINACAO = 0.25  # tolerância do ângulo de 45°: | |dx| − |dy| | ≤ 25% do comprimento
ENCAIXE = 1.5  # distância máxima (pt) entre a ponta da linha e o centro do tracinho

Segmento = tuple[float, float, float, float]


def _segmentos(pagina: pymupdf.Page) -> list[Segmento]:
    segmentos = []
    for desenho in pagina.get_drawings():
        for item in desenho["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                segmentos.append((a.x, a.y, b.x, b.y))
    return segmentos


def linhas_de_cota(pagina: pymupdf.Page) -> list[Segmento]:
    """Linhas de cota da página, como (x0, y0, x1, y1) em pontos, com x0 ≤ x1 e y0 ≤ y1."""
    segmentos = _segmentos(pagina)
    centros_de_tracinho = []
    for x0, y0, x1, y1 in segmentos:
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        comprimento = math.hypot(dx, dy)
        if TRACINHO_MIN <= comprimento <= TRACINHO_MAX and abs(dx - dy) <= INCLINACAO * comprimento:
            centros_de_tracinho.append(((x0 + x1) / 2, (y0 + y1) / 2))

    def tem_tracinho(x: float, y: float) -> bool:
        return any(math.hypot(x - cx, y - cy) <= ENCAIXE for cx, cy in centros_de_tracinho)

    cotas = set()
    for x0, y0, x1, y1 in segmentos:
        horizontal, vertical = abs(y1 - y0) < 0.5, abs(x1 - x0) < 0.5
        if not (horizontal or vertical) or math.hypot(x1 - x0, y1 - y0) <= TRACINHO_MAX:
            continue
        if tem_tracinho(x0, y0) and tem_tracinho(x1, y1):
            cotas.add((round(min(x0, x1), 2), round(min(y0, y1), 2),
                       round(max(x0, x1), 2), round(max(y0, y1), 2)))
    return sorted(cotas)
