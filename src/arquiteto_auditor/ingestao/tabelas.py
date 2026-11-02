"""Tabelas desenhadas nos PDFs de texto selecionável (leis, normas): grade e texto das células.

O PyMuPDF (find_tables) acha a GRADE pelas linhas desenhadas, mas o texto que ele devolve
para cada célula pode vir embaralhado quando o texto quebra dentro de uma coluna estreita
("3600\\n,\\n0" no lugar de "360,00"). Por isso usamos só a grade e preenchemos cada célula com
as palavras que o LeitorPDF já leu (com posição): a palavra pertence à célula que contém o
centro dela.

Célula mesclada (ex.: a zona ocupando 10 linhas de parâmetros) aparece uma vez só, na
primeira linha que ocupa, com a caixa inteira; nas linhas de baixo a posição fica vazia.

Páginas escaneadas não passam por aqui: no OCR não há linhas desenhadas (a tabela vira
linhas de texto comuns).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from arquiteto_auditor.dominio.documento import DocumentoLido, Palavra, TipoPagina

# Dois pedaços de número quebrados em linhas ("360,0" + "0") se juntam sem espaço.
_FIM_NUMERICO = re.compile(r"[\d.,]$")
_INICIO_NUMERICO = re.compile(r"^[\d.,]")


@dataclass(frozen=True)
class Celula:
    linha: int
    coluna: int
    bbox: tuple[float, float, float, float]
    palavras: tuple[Palavra, ...]
    ate_linha: int  # última linha que a célula ocupa (maior que "linha" quando mesclada)

    @property
    def texto(self) -> str:
        return juntar_linhas_da_celula(self.palavras)


@dataclass(frozen=True)
class Tabela:
    pagina: int
    linhas: int
    colunas: int
    celulas: tuple[Celula, ...]

    def celula(self, linha: int, coluna: int) -> Celula | None:
        """A célula que ocupa a posição (a mesclada vale para todas as linhas que cobre)."""
        for c in self.celulas:
            if c.coluna == coluna and c.linha <= linha <= c.ate_linha:
                return c
        return None


def juntar_linhas_da_celula(palavras: tuple[Palavra, ...] | list[Palavra]) -> str:
    """Texto da célula, linha por linha de cima para baixo."""
    if not palavras:
        return ""
    ordenadas = sorted(palavras, key=lambda p: (round(p.bbox[1]), p.bbox[0]))
    linhas: list[list[Palavra]] = []
    for p in ordenadas:
        if linhas and abs(p.bbox[1] - linhas[-1][0].bbox[1]) < (p.bbox[3] - p.bbox[1]) / 2:
            linhas[-1].append(p)
        else:
            linhas.append([p])
    texto = ""
    for linha in linhas:
        parte = " ".join(p.texto for p in sorted(linha, key=lambda p: p.bbox[0]))
        if texto and not (_FIM_NUMERICO.search(texto) and _INICIO_NUMERICO.search(parte)):
            texto += " "
        texto += parte
    return texto


def _dentro(palavra: Palavra, bbox: tuple[float, float, float, float]) -> bool:
    x = (palavra.bbox[0] + palavra.bbox[2]) / 2
    y = (palavra.bbox[1] + palavra.bbox[3]) / 2
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def ler_tabelas(caminho: Path, documento: DocumentoLido) -> list[Tabela]:
    """Tabelas de todas as páginas vetoriais do documento já lido."""
    tabelas = []
    vetoriais = {p.numero: p for p in documento.paginas if p.tipo == TipoPagina.VETORIAL}
    with pymupdf.open(caminho) as pdf:
        for numero, lida in vetoriais.items():
            for encontrada in pdf[numero - 1].find_tables().tables:
                topos = [linha.bbox[1] for linha in encontrada.rows]
                celulas = []
                for i, linha in enumerate(encontrada.rows):
                    for j, caixa in enumerate(linha.cells):
                        if caixa is None:
                            continue
                        bbox = tuple(float(v) for v in caixa)
                        palavras = tuple(p for p in lida.palavras if _dentro(p, bbox))
                        # Mesclada: vai até a última linha cujo topo fica dentro da caixa.
                        ate = max(k for k, topo in enumerate(topos)
                                  if k == i or bbox[1] <= topo < bbox[3] - 1)
                        celulas.append(Celula(i, j, bbox, palavras, ate))
                tabelas.append(Tabela(numero, encontrada.row_count, encontrada.col_count,
                                      tuple(celulas)))
    return tabelas
