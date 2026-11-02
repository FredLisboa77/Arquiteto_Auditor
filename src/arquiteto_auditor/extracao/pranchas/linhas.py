"""Agrupa as palavras de uma página em linhas de texto, só pela posição.

Serve para as três fontes de texto juntas (selecionável, comentários do AutoCAD e OCR): numa
prancha, o rótulo pode estar em texto e o valor num comentário (docs/06 §1). Passos:
1. fileiras: palavras com o centro vertical próximo (meia altura de letra) ficam juntas;
2. dentro da fileira, da esquerda para a direita, um espaço maior que ~1,5 altura de letra
   separa duas linhas (ex.: o rótulo "MUNICÍPIO:" e o valor, mais à direita).

Texto girado 90° (cotas verticais, lidas de baixo para cima) chega como palavras "em pé"
(mais altas que largas, com 2 letras ou mais; uma palavra curta e quase quadrada, como "DE",
conta quando está na mesma coluna e colada a uma palavra em pé). Elas passam pelo mesmo
agrupamento com as coordenadas giradas e viram linhas com vertical=True.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from arquiteto_auditor.dominio.documento import Palavra

FOLGA_VERTICAL = 0.5  # fração da altura da letra
ESPACO_MAXIMO = 1.5  # espaço entre palavras da mesma linha, em alturas de letra


@dataclass(frozen=True)
class LinhaTexto:
    palavras: tuple[Palavra, ...]  # em ordem de leitura
    vertical: bool = False  # texto girado 90° (lido de baixo para cima)

    @property
    def texto(self) -> str:
        return " ".join(p.texto for p in self.palavras)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return uniao_bbox(p.bbox for p in self.palavras)

    @property
    def altura(self) -> float:
        """Altura da letra (no texto girado, é a largura da palavra em pé)."""
        lado = 0 if self.vertical else 1
        return statistics.median(p.bbox[2 + lado] - p.bbox[lado] for p in self.palavras)

    @property
    def centro_y(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def confianca(self) -> float:
        return min(p.confianca for p in self.palavras)


def uniao_bbox(caixas) -> tuple[float, float, float, float]:
    """Menor retângulo que contém todas as caixas (x0, y0, x1, y1)."""
    caixas = list(caixas)
    return (min(c[0] for c in caixas), min(c[1] for c in caixas),
            max(c[2] for c in caixas), max(c[3] for c in caixas))


Caixa = tuple[float, float, float, float]


def _em_pe(p: Palavra) -> bool:
    largura, altura = p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]
    return len(p.texto) >= 2 and altura > 1.5 * largura


def _junto_de_palavra_em_pe(p: Palavra, em_pe: list[Palavra]) -> bool:
    """Palavra curta ("DE", "A") na mesma coluna e colada a uma palavra em pé."""
    largura = p.bbox[2] - p.bbox[0]
    return any(abs(p.bbox[0] - q.bbox[0]) <= 0.2 * largura
               and abs(p.bbox[2] - q.bbox[2]) <= 0.2 * largura
               and min(abs(p.bbox[1] - q.bbox[3]), abs(q.bbox[1] - p.bbox[3])) <= largura
               for q in em_pe)


def _girar(c: Caixa) -> Caixa:
    """Gira 90°: o texto em pé, lido de baixo para cima, fica deitado (esquerda → direita)."""
    return (-c[3], c[0], -c[1], c[2])


def _agrupar(itens: list[tuple[Caixa, Palavra]]) -> list[list[Palavra]]:
    """Fileiras e linhas (ver o início do módulo) a partir de caixas já deitadas."""
    def altura(c: Caixa) -> float:
        return max(c[3] - c[1], 0.1)

    def centro(c: Caixa) -> float:
        return (c[1] + c[3]) / 2

    fileiras: list[list[tuple[Caixa, Palavra]]] = []
    for item in sorted(itens, key=lambda i: centro(i[0])):
        if fileiras:
            ultima = fileiras[-1]
            meio = statistics.fmean(centro(c) for c, _ in ultima)
            alt = statistics.median(altura(c) for c, _ in ultima)
            if abs(centro(item[0]) - meio) <= FOLGA_VERTICAL * max(alt, altura(item[0])):
                ultima.append(item)
                continue
        fileiras.append([item])

    linhas: list[list[Palavra]] = []
    for fileira in fileiras:
        atual: list[tuple[Caixa, Palavra]] = []
        for item in sorted(fileira, key=lambda i: i[0][0]):
            if atual:
                espaco = item[0][0] - atual[-1][0][2]
                if espaco > ESPACO_MAXIMO * min(altura(item[0]), altura(atual[-1][0])):
                    linhas.append([p for _, p in atual])
                    atual = []
            atual.append(item)
        linhas.append([p for _, p in atual])
    return linhas


def agrupar_linhas(palavras: list[Palavra]) -> list[LinhaTexto]:
    """Linhas de texto em ordem de leitura (de cima para baixo, da esquerda para a direita)."""
    pe = [p for p in palavras if _em_pe(p)]
    pe += [p for p in palavras if not _em_pe(p) and _junto_de_palavra_em_pe(p, pe)]
    deitadas = [(p.bbox, p) for p in palavras if not any(p is q for q in pe)]
    em_pe = [(_girar(p.bbox), p) for p in pe]
    linhas = [LinhaTexto(tuple(grupo)) for grupo in _agrupar(deitadas)]
    linhas += [LinhaTexto(tuple(grupo), vertical=True) for grupo in _agrupar(em_pe)]
    return sorted(linhas, key=lambda ln: (round(ln.centro_y), ln.bbox[0]))
