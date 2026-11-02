"""Texto corrido de um documento, ligado de volta às páginas e às palavras.

Matrícula, escritura e memorial são lidos como TEXTO (frases, atos que passam de uma página
para outra), mas toda conclusão precisa de evidência com página e posição (CLAUDE.md §3).
Esta classe junta as linhas de todas as páginas num texto só e, para qualquer trecho dele,
devolve a página, o retângulo das linhas e a menor confiança do OCR das palavras.
"""

from __future__ import annotations

from dataclasses import dataclass

from arquiteto_auditor.dominio.documento import DocumentoLido, OrigemPalavra, Palavra
from arquiteto_auditor.dominio.modelos import Evidencia
from arquiteto_auditor.extracao.pranchas.linhas import uniao_bbox

LIMITE_TRECHO = 300  # caracteres guardados na evidência


@dataclass(frozen=True)
class _Linha:
    inicio: int  # posição no texto corrido
    fim: int
    pagina: int
    palavras: tuple[Palavra, ...]


class TextoCorrido:
    def __init__(self, documento: DocumentoLido):
        partes: list[str] = []
        self._linhas: list[_Linha] = []
        posicao = 0
        for pagina in documento.paginas:
            grupos: dict[tuple[int, int], list[Palavra]] = {}
            for palavra in pagina.palavras:
                grupos.setdefault((palavra.bloco, palavra.linha), []).append(palavra)
            for _, palavras in sorted(grupos.items()):
                texto = " ".join(p.texto for p in palavras)
                if partes:
                    posicao += 1  # o "\n" entre as linhas
                self._linhas.append(_Linha(posicao, posicao + len(texto), pagina.numero,
                                           tuple(palavras)))
                partes.append(texto)
                posicao += len(texto)
        self.texto = "\n".join(partes)

    def _linhas_do_trecho(self, inicio: int, fim: int) -> list[_Linha]:
        return [ln for ln in self._linhas if ln.inicio < fim and ln.fim > inicio]

    def confianca(self, inicio: int, fim: int) -> float | None:
        """Menor confiança do OCR nas palavras do trecho (None se não há palavra de OCR)."""
        valores = [p.confianca for ln in self._linhas_do_trecho(inicio, fim)
                   for p in ln.palavras if p.origem == OrigemPalavra.OCR]
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
