"""Leitura de PDFs: cada página vira uma lista única de palavras com posição e confiança.

Para cada página:
1. texto selecionável (PyMuPDF), com a posição de cada palavra;
2. comentários do PDF com texto (o AutoCAD grava ali o texto em fonte SHX, que no desenho
   virou traços — docs/06 §1);
3. OCR (Tesseract) quando a página é uma imagem (escaneada) e também nas imagens grandes
   embutidas numa página vetorial (ex.: quadro de áreas colado como imagem — docs/06 §6.2).

Página escaneada = quase sem texto e sem comentários, e com imagem cobrindo a maior parte da
folha. Página sem texto e sem imagem (ex.: perspectiva) é vetorial.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf
from PIL import Image

from arquiteto_auditor.config import ConfigOCR, config_ocr, pasta_de_dados
from arquiteto_auditor.dominio.documento import (
    DocumentoLido,
    OrigemPalavra,
    PaginaLida,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.ingestao.classificador import classificar
from arquiteto_auditor.ocr.cache import CacheOCR
from arquiteto_auditor.ocr.tesseract import ler_imagem

MINIMO_CARACTERES_VETORIAIS = 20  # abaixo disso, a página "não tem texto"
COBERTURA_ESCANEADA = 0.5  # fração da folha coberta por imagem numa página escaneada
COBERTURA_IMAGEM_PARA_OCR = 0.02  # imagens menores (logotipos, rubricas) não passam por OCR
BLOCO_COMENTARIOS = 100_000  # comentários e OCR de imagens ficam em blocos à parte
BLOCO_IMAGENS = 200_000


def hash_do_arquivo(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _palavras_vetoriais(pagina: pymupdf.Page) -> list[Palavra]:
    return [Palavra(texto=t, bbox=(x0, y0, x1, y1), confianca=1.0,
                    origem=OrigemPalavra.VETORIAL, bloco=b, linha=ln)
            for x0, y0, x1, y1, t, b, ln, _ in pagina.get_text("words") if t.strip()]


def _palavras_dos_comentarios(pagina: pymupdf.Page) -> list[Palavra]:
    """Cada comentário vira palavras; a posição de cada uma é estimada dentro do retângulo."""
    palavras = []
    for indice, anotacao in enumerate(pagina.annots()):
        conteudo = (anotacao.info.get("content") or "").strip()
        if not conteudo:
            continue
        r = anotacao.rect
        vertical = r.height > r.width * 1.5  # texto girado 90°
        comprimento = r.height if vertical else r.width
        total = max(1, len(conteudo))
        posicao = 0
        for token in conteudo.split():
            inicio = conteudo.index(token, posicao)
            posicao = inicio + len(token)
            a, b = comprimento * inicio / total, comprimento * posicao / total
            bbox = ((r.x0, r.y1 - b, r.x1, r.y1 - a) if vertical
                    else (r.x0 + a, r.y0, r.x0 + b, r.y1))
            palavras.append(Palavra(texto=token, bbox=bbox, confianca=1.0,
                                    origem=OrigemPalavra.COMENTARIO,
                                    bloco=BLOCO_COMENTARIOS + indice, linha=0))
    return palavras


def _retangulos_de_imagens(pagina: pymupdf.Page) -> list[tuple[pymupdf.Rect, int]]:
    """(retângulo na página, largura da imagem em pixels) de cada imagem desenhada."""
    retangulos = []
    for info in pagina.get_images(full=True):
        for rect in pagina.get_image_rects(info[0]):
            if rect.is_valid and not rect.is_empty:
                retangulos.append((rect & pagina.rect, info[2]))
    return retangulos


class LeitorPDF:
    def __init__(self, config: ConfigOCR | None = None, pasta_cache: Path | None = None,
                 usar_ocr: bool = True):
        self.config = config or config_ocr()
        self.cache = CacheOCR(pasta_cache or pasta_de_dados() / "cache" / "ocr")
        self.usar_ocr = usar_ocr

    def _ocr(self, pagina: pymupdf.Page, hash_documento: str, nome: str,
             clip: pymupdf.Rect | None = None) -> list:
        """OCR de uma região da página (inteira, se clip=None), com cache."""
        palavras = self.cache.ler(hash_documento, nome, self.config.idioma)
        if palavras is None:
            pixmap = pagina.get_pixmap(dpi=self.config.dpi, clip=clip, colorspace=pymupdf.csRGB,
                                       alpha=False)
            imagem = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            palavras = ler_imagem(imagem, self.config.dpi, self.config)
            self.cache.gravar(hash_documento, nome, self.config.idioma, palavras)
        escala = 72 / self.config.dpi
        x, y = (clip.x0, clip.y0) if clip is not None else (0.0, 0.0)
        return [(p, (x + p.bbox[0] * escala, y + p.bbox[1] * escala,
                     x + p.bbox[2] * escala, y + p.bbox[3] * escala)) for p in palavras]

    def ler_pagina(self, pagina: pymupdf.Page, numero: int, hash_documento: str) -> PaginaLida:
        vetoriais = _palavras_vetoriais(pagina)
        comentarios = _palavras_dos_comentarios(pagina)
        imagens = _retangulos_de_imagens(pagina)
        area_folha = pagina.rect.width * pagina.rect.height
        cobertura = sum(r.width * r.height for r, _ in imagens) / area_folha
        caracteres = sum(len(p.texto) for p in vetoriais)
        escaneada = (caracteres < MINIMO_CARACTERES_VETORIAIS and not comentarios
                     and cobertura >= COBERTURA_ESCANEADA)

        lida = PaginaLida(numero=numero, largura=pagina.rect.width, altura=pagina.rect.height,
                          tipo=TipoPagina.ESCANEADA if escaneada else TipoPagina.VETORIAL,
                          palavras=vetoriais + comentarios,
                          desenhos=len(pagina.get_cdrawings()))
        if escaneada:
            maior = max(imagens, key=lambda item: item[0].width * item[0].height)
            lida.dpi_imagem = round(maior[1] / (maior[0].width / 72))
            if self.usar_ocr:
                lida.palavras = [self._palavra_ocr(p, bbox, 0)
                                 for p, bbox in self._ocr(pagina, hash_documento,
                                                          f"pagina_{numero}")]
        elif self.usar_ocr:
            grandes = [r for r, _ in imagens if r.width * r.height / area_folha
                       >= COBERTURA_IMAGEM_PARA_OCR]
            for indice, rect in enumerate(grandes):
                lidas = self._ocr(pagina, hash_documento, f"pagina_{numero}_imagem_{indice}",
                                  clip=rect)
                lida.palavras += [self._palavra_ocr(p, bbox, BLOCO_IMAGENS + indice * 1000)
                                  for p, bbox in lidas]
            lida.imagens_lidas_por_ocr = len(grandes)
        return lida

    @staticmethod
    def _palavra_ocr(p, bbox, deslocamento_bloco: int) -> Palavra:
        return Palavra(texto=p.texto, bbox=bbox, confianca=p.confianca, origem=OrigemPalavra.OCR,
                       bloco=deslocamento_bloco + p.bloco, linha=p.linha)

    def ler(self, caminho: Path) -> DocumentoLido:
        caminho = Path(caminho)
        hash_documento = hash_do_arquivo(caminho)
        with pymupdf.open(caminho) as documento:
            paginas = [self.ler_pagina(pagina, numero, hash_documento)
                       for numero, pagina in enumerate(documento, start=1)]
        lido = DocumentoLido(arquivo=caminho.name, hash_sha256=hash_documento, paginas=paginas)
        classificacao = classificar(lido)
        lido.tipo, lido.confianca_tipo = classificacao.tipo, classificacao.confianca
        lido.motivo_tipo = classificacao.motivo
        return lido
