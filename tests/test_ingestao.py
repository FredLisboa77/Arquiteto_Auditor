"""Testes da ingestão: palavras de texto, comentários e OCR; tipo de página; tipo de documento."""

import io

import pymupdf
import pytest
from PIL import Image, ImageDraw

from arquiteto_auditor.config import config_ocr
from arquiteto_auditor.dominio.documento import (
    DocumentoLido,
    OrigemPalavra,
    PaginaLida,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.dominio.modelos import TipoDocumento
from arquiteto_auditor.ingestao import leitor as modulo_leitor
from arquiteto_auditor.ingestao.classificador import classificar
from arquiteto_auditor.ingestao.leitor import BLOCO_IMAGENS, LeitorPDF
from dados_sinteticos.geradores.escaneado import _fonte

tesseract = pytest.mark.skipif(not config_ocr().tesseract_cmd,
                               reason="Tesseract não instalado nesta máquina")


def _imagem_de_texto(texto: str, largura=1400, altura=300) -> bytes:
    """Imagem com uma linha de texto (use largura=1240, altura=1754 para uma página A4)."""
    imagem = Image.new("RGB", (largura, altura), "white")
    ImageDraw.Draw(imagem).text((40, 100), texto, font=_fonte("arial", False, 48), fill="black")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def _salvar(documento, tmp_path, nome="teste.pdf"):
    caminho = tmp_path / nome
    documento.save(caminho)
    return caminho


@pytest.fixture
def leitor(tmp_path):
    return LeitorPDF(pasta_cache=tmp_path / "cache")


def test_pagina_vetorial_com_texto(leitor, tmp_path):
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 100), "ÁREA DO TERRENO 450,00 m²")
    lido = leitor.ler(_salvar(documento, tmp_path))
    pagina = lido.paginas[0]
    assert pagina.tipo == TipoPagina.VETORIAL
    assert [p.texto for p in pagina.palavras][:3] == ["ÁREA", "DO", "TERRENO"]
    assert all(p.origem == OrigemPalavra.VETORIAL and p.confianca == 1 for p in pagina.palavras)
    assert len(lido.hash_sha256) == 64


def test_texto_dos_comentarios_entra_na_lista_de_palavras(leitor, tmp_path):
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.draw_line((50, 50), (300, 50))  # o "texto SHX" é desenho
    anotacao = pagina.add_rect_annot(pymupdf.Rect(100, 200, 300, 215))
    anotacao.set_info(content="A=31.15m² C=0.95")
    anotacao.update()
    lida = leitor.ler(_salvar(documento, tmp_path)).paginas[0]
    assert lida.tipo == TipoPagina.VETORIAL
    palavras = [p for p in lida.palavras if p.origem == OrigemPalavra.COMENTARIO]
    assert [p.texto for p in palavras] == ["A=31.15m²", "C=0.95"]
    assert palavras[0].bbox[2] <= palavras[1].bbox[0] + 1  # posições estimadas em sequência
    assert all(99 <= p.bbox[0] and p.bbox[2] <= 301 for p in palavras)  # + borda do comentário


@tesseract
def test_pagina_escaneada_passa_pelo_ocr_e_usa_cache(leitor, tmp_path, monkeypatch):
    documento = pymupdf.open()
    pagina = documento.new_page(width=595, height=842)
    pagina.insert_image(pagina.rect, stream=_imagem_de_texto("MATRICULA 12.345", 1240, 1754))
    caminho = _salvar(documento, tmp_path)
    lida = leitor.ler(caminho).paginas[0]
    assert lida.tipo == TipoPagina.ESCANEADA and lida.dpi_imagem
    assert any("12.345" in p.texto for p in lida.palavras)
    assert all(p.origem == OrigemPalavra.OCR for p in lida.palavras)
    # 2ª leitura: vem do cache, sem chamar o Tesseract
    monkeypatch.setattr(modulo_leitor, "ler_imagem", lambda *a, **k: pytest.fail("sem cache"))
    assert leitor.ler(caminho).paginas[0].palavras == lida.palavras


@tesseract
def test_imagem_embutida_em_pagina_vetorial_passa_pelo_ocr(leitor, tmp_path):
    documento = pymupdf.open()
    pagina = documento.new_page(width=595, height=842)
    pagina.insert_text((72, 80), "MEMORIAL DESCRITIVO - Quadro de áreas:")
    pagina.insert_image(pymupdf.Rect(72, 120, 520, 220),
                        stream=_imagem_de_texto("TOTAL 283,41 m2"))
    lida = leitor.ler(_salvar(documento, tmp_path)).paginas[0]
    assert lida.tipo == TipoPagina.VETORIAL and lida.imagens_lidas_por_ocr == 1
    da_imagem = [p for p in lida.palavras if p.bloco >= BLOCO_IMAGENS]
    assert any("283" in p.texto for p in da_imagem)
    assert all(120 - 5 <= p.bbox[1] and p.bbox[3] <= 220 + 5 for p in da_imagem)


def test_sem_ocr_a_pagina_escaneada_fica_sem_palavras(tmp_path):
    documento = pymupdf.open()
    pagina = documento.new_page(width=595, height=842)
    pagina.insert_image(pagina.rect, stream=_imagem_de_texto("TEXTO", 1240, 1754))
    leitor = LeitorPDF(pasta_cache=tmp_path / "cache", usar_ocr=False)
    lida = leitor.ler(_salvar(documento, tmp_path)).paginas[0]
    assert lida.tipo == TipoPagina.ESCANEADA and lida.palavras == []


# ---------------------------------------------------------------- tipo de documento


def _documento(texto: str, largura=595.0, altura=842.0, desenhos=0) -> DocumentoLido:
    palavras = [Palavra(texto=t, bbox=(0, 0, 1, 1), confianca=1, origem="vetorial", linha=i)
                for i, t in enumerate(texto.split())]
    pagina = PaginaLida(numero=1, largura=largura, altura=altura, tipo="vetorial",
                        palavras=palavras, desenhos=desenhos)
    return DocumentoLido(arquivo="x.pdf", hash_sha256="0" * 64, paginas=[pagina])


@pytest.mark.parametrize("texto, tipo", [
    ("REGISTRO DE IMÓVEIS LIVRO Nº 2 - REGISTRO GERAL MATRÍCULA Nº 1.234 "
     "R-1/1.234 COMPRA E VENDA O Oficial.", TipoDocumento.MATRICULA),
    ("CERTIDÃO DE INTEIRO TEOR MATRÍCULA Nº 9.876", TipoDocumento.MATRICULA),
    ("ESCRITURA PÚBLICA DE COMPRA E VENDA SAIBAM quantos esta pública escritura virem "
     "OUTORGANTE VENDEDOR OUTORGADO COMPRADOR Tabelionato", TipoDocumento.ESCRITURA),
    ("MEMORIAL DESCRITIVO Trata-se de uma edificação unifamiliar", TipoDocumento.MEMORIAL),
    ("LEI COMPLEMENTAR Nº 123 Dispõe sobre o uso do solo. O PREFEITO MUNICIPAL Art. 1º "
     "Art. 2º ZONEAMENTO ANEXO II", TipoDocumento.LEI_MUNICIPAL),
    ("REGULAMENTO DE OBRAS do condomínio aprovado em ASSEMBLEIA. COMISSÃO DE OBRAS. "
     "O condômino. Síndico", TipoDocumento.NORMA_CONDOMINIO),
])
def test_classifica_pelo_texto(texto, tipo):
    resultado = classificar(_documento(texto))
    assert resultado.tipo == tipo and resultado.confianca > 0


def test_prancha_sem_texto_e_reconhecida_pelo_formato_e_desenho():
    resultado = classificar(_documento("", largura=2384, altura=1684, desenhos=3000))
    assert resultado.tipo == TipoDocumento.PRANCHA


def test_sem_pistas_o_tipo_fica_outro():
    resultado = classificar(_documento("texto qualquer sem pistas"))
    assert resultado.tipo == TipoDocumento.OUTRO and resultado.confianca == 0


# ---------------------------------------------------------------- linhas de cota desenhadas

from arquiteto_auditor.ingestao.geometria import linhas_de_cota  # noqa: E402


def _cota(pagina, x0, y0, x1, y1, tracinho=4.0):
    """Linha de cota com um tracinho a 45° em cada ponta (estilo arquitetônico)."""
    pagina.draw_line((x0, y0), (x1, y1))
    for x, y in ((x0, y0), (x1, y1)):
        pagina.draw_line((x - tracinho, y + tracinho), (x + tracinho, y - tracinho))


def test_linhas_de_cota_sao_segmentos_com_tracinhos_nas_duas_pontas(tmp_path):
    documento = pymupdf.open()
    pagina = documento.new_page(width=842, height=595)
    _cota(pagina, 100, 100, 300, 100)  # horizontal
    _cota(pagina, 400, 100, 400, 250)  # vertical
    pagina.draw_line((100, 400), (300, 400))  # linha comum: não é cota
    pagina.draw_line((500, 400), (510, 390))  # tracinho solto
    pagina.draw_rect(pymupdf.Rect(600, 300, 700, 380))  # retângulo: não é cota
    cotas = sorted(linhas_de_cota(pagina))
    assert cotas == [(100.0, 100.0, 300.0, 100.0), (400.0, 100.0, 400.0, 250.0)]


def test_pagina_vetorial_guarda_as_linhas_de_cota(leitor, tmp_path):
    caminho = tmp_path / "prancha.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page(width=842, height=595)
    pagina.insert_text((100, 90), "RECUO FRONTAL 5,00", fontsize=9)
    _cota(pagina, 100, 100, 300, 100)
    documento.save(caminho)
    assert leitor.ler(caminho).paginas[0].cotas_desenhadas == [(100.0, 100.0, 300.0, 100.0)]
