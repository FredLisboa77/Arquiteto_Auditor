"""Texto corrido de um documento, ligado de volta às páginas e às palavras.

Matrícula, escritura e memorial são lidos como TEXTO (frases, atos que passam de uma página
para outra), mas toda conclusão precisa de evidência com página e posição (CLAUDE.md §3).
Esta classe junta as linhas de todas as páginas num texto só e, para qualquer trecho dele,
devolve a página, o retângulo das linhas e a menor confiança do OCR das palavras.

Ordem das linhas: a do PDF no texto selecionável; nas páginas escaneadas (coluna única),
de cima para baixo — a numeração de blocos do OCR pode pôr um pedaço do parágrafo depois de
outro quando um carimbo o interrompe.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from arquiteto_auditor.dominio.documento import (
    DocumentoLido,
    OrigemPalavra,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.dominio.modelos import Evidencia
from arquiteto_auditor.extracao.pranchas.linhas import uniao_bbox

LIMITE_TRECHO = 300  # caracteres guardados na evidência


def normalizar(texto: str) -> str:
    """Maiúsculas sem acentos, com o MESMO tamanho: as posições continuam valendo."""
    saida = []
    for c in texto:
        base = unicodedata.normalize("NFD", c)[0]
        maiuscula = base.upper()
        saida.append(maiuscula if len(maiuscula) == 1 else base)  # "ß".upper() = "SS"
    return "".join(saida)


@dataclass(frozen=True)
class LinhaCorrida:
    inicio: int  # posição no texto corrido
    fim: int
    pagina: int
    palavras: tuple[Palavra, ...]
    posicoes: tuple[tuple[int, int], ...]  # (início, fim) de cada palavra no texto corrido


class TextoCorrido:
    def __init__(self, documento: DocumentoLido):
        partes: list[str] = []
        self._linhas: list[LinhaCorrida] = []
        posicao = 0
        for pagina in documento.paginas:
            grupos: dict[tuple[int, int], list[Palavra]] = {}
            for palavra in pagina.palavras:
                grupos.setdefault((palavra.bloco, palavra.linha), []).append(palavra)
            ordem = sorted(grupos.items())
            if pagina.tipo == TipoPagina.ESCANEADA:
                ordem.sort(key=lambda g: (min(p.bbox[1] for p in g[1]),
                                          min(p.bbox[0] for p in g[1])))
            for _, palavras in ordem:
                texto = " ".join(p.texto for p in palavras)
                if partes:
                    posicao += 1  # o "\n" entre as linhas
                posicoes, cursor = [], posicao
                for p in palavras:
                    posicoes.append((cursor, cursor + len(p.texto)))
                    cursor += len(p.texto) + 1
                self._linhas.append(LinhaCorrida(posicao, posicao + len(texto), pagina.numero,
                                           tuple(palavras), tuple(posicoes)))
                partes.append(texto)
                posicao += len(texto)
        self.texto = "\n".join(partes)

    @property
    def linhas(self) -> tuple[LinhaCorrida, ...]:
        """As linhas na ordem do texto, com página e palavras."""
        return tuple(self._linhas)

    def _linhas_do_trecho(self, inicio: int, fim: int) -> list[LinhaCorrida]:
        return [ln for ln in self._linhas if ln.inicio < fim and ln.fim > inicio]

    def confianca(self, inicio: int, fim: int) -> float | None:
        """Menor confiança do OCR nas palavras do trecho (None se não há palavra de OCR)."""
        valores = [p.confianca for ln in self._linhas_do_trecho(inicio, fim)
                   for p, (a, b) in zip(ln.palavras, ln.posicoes, strict=True)
                   if p.origem == OrigemPalavra.OCR and a < fim and b > inicio]
        return min(valores) if valores else None

    def pagina(self, posicao: int) -> int | None:
        linhas = self._linhas_do_trecho(posicao, posicao + 1)
        return linhas[0].pagina if linhas else None

    def evidencia(self, inicio: int, fim: int, arquivo: str) -> Evidencia:
        """Evidência do trecho: página onde começa, retângulo das linhas nessa página."""
        linhas = self._linhas_do_trecho(inicio, fim)
        if not linhas:
            raise ValueError("trecho fora do texto")
        primeira = linhas[0].pagina
        caixas = [p.bbox for ln in linhas if ln.pagina == primeira for p in ln.palavras]
        trecho = " ".join(self.texto[inicio:fim].split())
        if len(trecho) > LIMITE_TRECHO:
            trecho = trecho[:LIMITE_TRECHO].rstrip() + "…"
        return Evidencia(documento=arquivo, pagina=primeira, trecho=trecho,
                         bbox=uniao_bbox(caixas), confianca_ocr=self.confianca(inicio, fim))
