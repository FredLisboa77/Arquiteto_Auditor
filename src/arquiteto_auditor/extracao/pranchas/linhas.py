"""Agrupa as palavras de uma página em linhas de texto, só pela posição.

Serve para as três fontes de texto juntas (selecionável, comentários do AutoCAD e OCR): numa
prancha, o rótulo pode estar em texto e o valor num comentário (docs/06 §1). Passos:
1. fileiras: palavras com o centro vertical próximo (meia altura de letra) ficam juntas;
2. dentro da fileira, da esquerda para a direita, um espaço maior que ~1,5 altura de letra
   separa duas linhas (ex.: o rótulo "MUNICÍPIO:" e o valor, mais à direita).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from arquiteto_auditor.dominio.documento import Palavra

FOLGA_VERTICAL = 0.5  # fração da altura da letra
ESPACO_MAXIMO = 1.5  # espaço entre palavras da mesma linha, em alturas de letra


@dataclass(frozen=True)
class LinhaTexto:
    palavras: tuple[Palavra, ...]

    @property
    def texto(self) -> str:
        return " ".join(p.texto for p in self.palavras)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (min(p.bbox[0] for p in self.palavras), min(p.bbox[1] for p in self.palavras),
                max(p.bbox[2] for p in self.palavras), max(p.bbox[3] for p in self.palavras))

    @property
    def altura(self) -> float:
        return statistics.median(p.bbox[3] - p.bbox[1] for p in self.palavras)

    @property
    def centro_y(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def confianca(self) -> float:
        return min(p.confianca for p in self.palavras)


def _altura(p: Palavra) -> float:
    return max(p.bbox[3] - p.bbox[1], 0.1)


def _centro(p: Palavra) -> float:
    return (p.bbox[1] + p.bbox[3]) / 2


def agrupar_linhas(palavras: list[Palavra]) -> list[LinhaTexto]:
    """Linhas de texto em ordem de leitura (de cima para baixo, da esquerda para a direita)."""
    fileiras: list[list[Palavra]] = []
    for palavra in sorted(palavras, key=_centro):
        if fileiras:
            ultima = fileiras[-1]
            centro = statistics.fmean(_centro(p) for p in ultima)
            altura = statistics.median(_altura(p) for p in ultima)
            if abs(_centro(palavra) - centro) <= FOLGA_VERTICAL * max(altura, _altura(palavra)):
                ultima.append(palavra)
                continue
        fileiras.append([palavra])

    linhas: list[LinhaTexto] = []
    for fileira in fileiras:
        atual: list[Palavra] = []
        for palavra in sorted(fileira, key=lambda p: p.bbox[0]):
            if atual:
                espaco = palavra.bbox[0] - atual[-1].bbox[2]
                altura = min(_altura(palavra), _altura(atual[-1]))
                if espaco > ESPACO_MAXIMO * altura:
                    linhas.append(LinhaTexto(tuple(atual)))
                    atual = []
            atual.append(palavra)
        linhas.append(LinhaTexto(tuple(atual)))
    return sorted(linhas, key=lambda ln: (round(ln.centro_y), ln.bbox[0]))
