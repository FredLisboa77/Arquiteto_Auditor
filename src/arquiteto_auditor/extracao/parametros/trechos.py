"""Recorta uma lei ou norma de condomínio em trechos: artigos, itens numerados, parágrafos.

O LLM nunca recebe o documento inteiro (docs/03 §2.1): a busca escolhe alguns trechos e só
eles vão no pedido. Cada trecho guarda onde começa e termina no texto corrido, para que a
citação devolvida pelo LLM possa ser localizada e virar evidência com página e posição.

Regras do recorte:
- um trecho começa em "Art. 5º", num item numerado ("9.", "13.1.", e "4," do OCR) ou num
  título (CAPÍTULO, Seção, ANEXO, "IV. MUROS"); incisos, alíneas e parágrafos ficam no artigo;
- o título mais recente vai junto com o trecho (ex.: "Seção - Zona Residencial 2 (ZR-2)");
- cabeçalhos e rodapés repetidos nas páginas são deixados de fora;
- linhas dentro de tabelas desenhadas também (as tabelas são lidas célula a célula);
- trecho muito longo é dividido em pedaços nas quebras de linha.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from arquiteto_auditor.extracao.texto_corrido import LinhaCorrida, TextoCorrido, normalizar
from arquiteto_auditor.ingestao.tabelas import Tabela

TAMANHO_MAXIMO = 1500  # caracteres por trecho
LINHAS_DE_CABECALHO = 4  # primeiras linhas da página que podem ser cabeçalho
LINHAS_DE_RODAPE = 3

_ARTIGO = re.compile(r"^\W{0,2}ART\.?\s*\d+")
_ITEM = re.compile(r"^\W{0,2}\d{1,3}(\.\d{1,2})*[.,]\s+[A-Z]")  # já em normalizar(): maiúsculas
_TITULO = re.compile(r"^\W{0,2}(CAPITULO|SECAO|ANEXO|TITULO)\b")
_TITULO_ROMANO = re.compile(r"^\W{0,2}[IVXL|]{1,5}\s*[.-]\s+[A-Z ]+$")  # "IV. MUROS", "|. DISP"


@dataclass(frozen=True)
class Trecho:
    texto: str  # linhas do trecho juntas com espaço (sem cabeçalhos e rodapés)
    titulo: str  # título (capítulo, seção, anexo) em que o trecho está; "" se nenhum
    pagina: int  # página onde começa
    linhas: tuple[LinhaCorrida, ...]

    @property
    def inicio(self) -> int:
        return self.linhas[0].inicio

    @property
    def fim(self) -> int:
        return self.linhas[-1].fim


def _sem_digitos(texto: str) -> str:
    return re.sub(r"[\d\s]", "", normalizar(texto))


def linhas_de_cabecalho_e_rodape(corrido: TextoCorrido) -> set[int]:
    """Posições (início) das linhas de cabeçalho/rodapé.

    Contam só as primeiras e últimas linhas de cada página, com os números ignorados
    ("página 3" = "página 4"), repetidas em mais da metade das páginas (e em 2 ou mais):
    dois artigos parecidos no topo de duas páginas ("Na ZR-1, o ruído..." e "Na ZR-2, o
    ruído...") não são cabeçalho de uma lei de 20 páginas.
    """
    por_pagina: dict[int, list[LinhaCorrida]] = defaultdict(list)
    for linha in corrido.linhas:
        por_pagina[linha.pagina].append(linha)
    candidatas: dict[str, list[LinhaCorrida]] = defaultdict(list)
    for linhas in por_pagina.values():
        margens = linhas[:LINHAS_DE_CABECALHO] + linhas[-LINHAS_DE_RODAPE:]
        for linha in {ln.inicio: ln for ln in margens}.values():
            chave = _sem_digitos(corrido.texto[linha.inicio:linha.fim])
            if chave:
                candidatas[chave].append(linha)
    minimo = max(2, len(por_pagina) // 2 + 1)  # mais da metade
    repetidas = set()
    for linhas in candidatas.values():
        if len({ln.pagina for ln in linhas}) >= minimo:
            repetidas.update(ln.inicio for ln in linhas)
    return repetidas


def _dentro_de_tabela(linha: LinhaCorrida, tabelas: list[Tabela]) -> bool:
    for tabela in tabelas:
        if tabela.pagina != linha.pagina:
            continue
        for palavra in linha.palavras:
            x = (palavra.bbox[0] + palavra.bbox[2]) / 2
            y = (palavra.bbox[1] + palavra.bbox[3]) / 2
            if any(c.bbox[0] <= x <= c.bbox[2] and c.bbox[1] <= y <= c.bbox[3]
                   for c in tabela.celulas):
                return True
    return False


def tipo_da_linha(texto: str) -> str:
    """'artigo', 'item', 'titulo' ou 'continuacao'."""
    normal = normalizar(texto.strip())
    if _ARTIGO.match(normal):
        return "artigo"
    if _TITULO.match(normal) or _TITULO_ROMANO.match(normal):
        return "titulo"
    if _ITEM.match(normal):
        return "item"
    return "continuacao"


def _texto(corrido: TextoCorrido, linhas: list[LinhaCorrida]) -> str:
    return " ".join(" ".join(corrido.texto[ln.inicio:ln.fim].split()) for ln in linhas)


def recortar(corrido: TextoCorrido, tabelas: list[Tabela] | None = None) -> list[Trecho]:
    """Trechos do documento, na ordem em que aparecem."""
    fora = linhas_de_cabecalho_e_rodape(corrido)
    grupos: list[tuple[str, list[LinhaCorrida]]] = []  # (título, linhas)
    titulo = ""
    for linha in corrido.linhas:
        if linha.inicio in fora or _dentro_de_tabela(linha, tabelas or []):
            continue
        tipo = tipo_da_linha(corrido.texto[linha.inicio:linha.fim])
        if tipo == "titulo":
            titulo = " ".join(corrido.texto[linha.inicio:linha.fim].split())
            grupos.append((titulo, [linha]))
        elif tipo in ("artigo", "item") or not grupos:
            grupos.append((titulo, [linha]))
        else:
            grupos[-1][1].append(linha)

    trechos = []
    for titulo_do_grupo, linhas in grupos:
        pedaco: list[LinhaCorrida] = []
        for linha in linhas:
            if pedaco and len(_texto(corrido, pedaco + [linha])) > TAMANHO_MAXIMO:
                trechos.append(Trecho(_texto(corrido, pedaco), titulo_do_grupo,
                                      pedaco[0].pagina, tuple(pedaco)))
                pedaco = []
            pedaco.append(linha)
        trechos.append(Trecho(_texto(corrido, pedaco), titulo_do_grupo, pedaco[0].pagina,
                              tuple(pedaco)))
    return trechos
