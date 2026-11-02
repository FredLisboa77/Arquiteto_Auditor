"""Recorte da evidência: a imagem do trecho da página de onde saiu um valor.

Usado na tela de pendências (docs/02 §2.3), para o revisor ver o valor no próprio documento.
A região da evidência (bbox) é renderizada com uma margem de contexto e destacada com um
retângulo vermelho, desenhado SÓ NA IMAGEM: o PDF é aberto para leitura e nunca alterado
(CLAUDE.md §3). Evidência sem bbox → a página inteira.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from arquiteto_auditor.dominio.modelos import Evidencia

MARGEM_PT = 30.0  # contexto em volta do trecho (pontos; 1 pt = 1/72 polegada)
MINIMO_PT = (300.0, 200.0)  # recorte mínimo (largura, altura): uma cota solta precisa do lote
DPI = 150
COR_DESTAQUE = (220, 30, 30)


def recortar_evidencia(caminho_pdf: Path, evidencia: Evidencia, margem: float = MARGEM_PT,
                       dpi: int = DPI,
                       minimo: tuple[float, float] = MINIMO_PT) -> bytes:
    """PNG da região da evidência, com o trecho destacado."""
    with pymupdf.open(caminho_pdf) as documento:
        pagina = documento[evidencia.pagina - 1]
        if evidencia.bbox is None:
            regiao = pagina.rect
        else:
            x0, y0, x1, y1 = evidencia.bbox
            folga_x = max(margem, (minimo[0] - (x1 - x0)) / 2)
            folga_y = max(margem, (minimo[1] - (y1 - y0)) / 2)
            regiao = pymupdf.Rect(x0 - folga_x, y0 - folga_y, x1 + folga_x, y1 + folga_y)
            regiao &= pagina.rect  # não sai da página
        pixmap = pagina.get_pixmap(dpi=dpi, clip=regiao, colorspace=pymupdf.csRGB, alpha=False)
    imagem = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    if evidencia.bbox is not None:
        escala = dpi / 72
        x0, y0, x1, y1 = evidencia.bbox
        caixa = [(x0 - regiao.x0) * escala, (y0 - regiao.y0) * escala,
                 (x1 - regiao.x0) * escala, (y1 - regiao.y0) * escala]
        ImageDraw.Draw(imagem).rectangle(caixa, outline=COR_DESTAQUE,
                                         width=max(2, round(escala)))
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()
