"""Testes do OCR (Tesseract), da medida de erro (CER) e do cache."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from arquiteto_auditor.avaliacao.ocr import cer, distancia_edicao, separar_erros
from arquiteto_auditor.config import config_ocr
from arquiteto_auditor.ocr.cache import CacheOCR
from arquiteto_auditor.ocr.tesseract import (
    PalavraOCR,
    apagar_grade,
    estimar_inclinacao,
    ler_imagem,
)
from dados_sinteticos.geradores.escaneado import _fonte

tesseract = pytest.mark.skipif(not config_ocr().tesseract_cmd,
                               reason="Tesseract não instalado nesta máquina")

LINHAS = ["MATRÍCULA Nº 12.345 - LIVRO 2", "IMÓVEL: lote com a área de 450,00 m²",
          "situado na Rua das Acácias, 120, município de Vila Nova."]


def _pagina(dpi=200, angulo=0.0) -> tuple[Image.Image, dict[str, tuple]]:
    """Imagem de texto (Arial) e a caixa onde cada palavra foi desenhada."""
    escala = dpi / 72
    imagem = Image.new("L", (round(500 * escala), round(160 * escala)), 255)
    d = ImageDraw.Draw(imagem)
    fonte = _fonte("arial", False, round(11 * escala))
    caixas = {}
    for i, linha in enumerate(LINHAS):
        x, y = 30 * escala, (30 + 30 * i) * escala
        for palavra in linha.split():
            caixa = d.textbbox((x, y), palavra, font=fonte)
            d.text((x, y), palavra, font=fonte, fill=0)
            caixas[palavra] = caixa
            x = caixa[2] + fonte.getlength(" ")
    if angulo:
        imagem = imagem.rotate(angulo, resample=Image.BICUBIC, fillcolor=255)
    return imagem, caixas


def test_distancia_de_edicao_e_cer():
    assert distancia_edicao("casa", "casa") == 0
    assert distancia_edicao("casa", "cama") == 1
    assert distancia_edicao("", "abc") == 3
    assert distancia_edicao("kitten", "sitting") == 3
    assert cer("lote 450,00  m²", "lote 450,00 m²") == 0  # espaços extras não contam
    assert cer("lote 45O,00 m²", "lote 450,00 m²") == pytest.approx(1 / 14)


@pytest.mark.parametrize("angulo", [-2.0, 0.0, 1.5])
def test_estimar_inclinacao(angulo):
    imagem, _ = _pagina(angulo=angulo)
    assert estimar_inclinacao(np.asarray(imagem)) == pytest.approx(angulo, abs=0.4)


@tesseract
def test_ocr_le_palavras_com_posicao_e_confianca():
    imagem, caixas = _pagina()
    palavras = ler_imagem(imagem, 200)
    texto = " ".join(p.texto for p in palavras)
    assert cer(texto, " ".join(LINHAS)) < 0.05
    area = next(p for p in palavras if p.texto == "450,00")
    esperada = caixas["450,00"]
    assert all(abs(a - b) < 15 for a, b in zip(area.bbox, esperada, strict=True))
    assert 0.5 < area.confianca <= 1


@tesseract
def test_ocr_corrige_inclinacao_e_devolve_posicao_na_imagem_original():
    imagem, _ = _pagina(angulo=2.0)
    palavras = ler_imagem(imagem, 200)
    assert cer(" ".join(p.texto for p in palavras), " ".join(LINHAS)) < 0.08
    for p in palavras:  # as caixas ficam dentro da imagem original
        assert 0 <= p.bbox[0] < p.bbox[2] <= imagem.width + 5
        assert 0 <= p.bbox[1] < p.bbox[3] <= imagem.height + 5


@tesseract
def test_ocr_amplia_imagens_de_baixa_resolucao():
    imagem, _ = _pagina(dpi=135)
    palavras = ler_imagem(imagem, 135)
    assert cer(" ".join(p.texto for p in palavras), " ".join(LINHAS)) < 0.08
    assert max(p.bbox[2] for p in palavras) <= imagem.width + 5  # posição na escala original


def test_cache_grava_e_le(tmp_path):
    cache = CacheOCR(tmp_path)
    palavras = [PalavraOCR("ÁREA", (1.0, 2.0, 3.0, 4.0), 0.9, 1, 1001)]
    assert cache.ler("a" * 64, "pagina_1", "por") is None
    cache.gravar("a" * 64, "pagina_1", "por", palavras)
    assert cache.ler("a" * 64, "pagina_1", "por") == palavras
    assert cache.ler("a" * 64, "pagina_1", "eng") is None  # outro idioma, outra entrada


def test_imagem_de_teste_e_valida():
    imagem, caixas = _pagina()
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    assert buffer.getvalue() and "MATRÍCULA" in caixas


QUADRO = [("Área do terreno", "375,00 m²"), ("Área construída total", "161,34 m²"),
          ("Taxa de ocupação", "25,01 %"), ("Coeficiente de aproveitamento", "0,45")]


def _tabela(dpi=300) -> Image.Image:
    """Quadro de áreas com grade (linhas de tabela), como os colados em memoriais."""
    escala = dpi / 72
    largura, altura_linha = round(340 * escala), round(18 * escala)
    imagem = Image.new("L", (largura, altura_linha * len(QUADRO) + 2), 255)
    d = ImageDraw.Draw(imagem)
    fonte = _fonte("arial", False, round(10 * escala))
    divisa = round(230 * escala)
    for i, (rotulo, valor) in enumerate(QUADRO):
        y = i * altura_linha
        d.rectangle((0, y, largura - 1, y + altura_linha), outline=0, width=2)
        d.line((divisa, y, divisa, y + altura_linha), fill=0, width=2)
        d.text((6 * escala, y + 4 * escala), rotulo, font=fonte, fill=0)
        d.text((divisa + 6 * escala, y + 4 * escala), valor, font=fonte, fill=0)
    return imagem


def test_apagar_grade_remove_linhas_e_mantem_texto():
    imagem = _tabela()
    limpa = np.asarray(apagar_grade(imagem.convert("L")))
    tinta = limpa < 128
    assert tinta.mean(axis=1).max() < 0.5  # nenhuma linha horizontal atravessa a imagem
    assert tinta.mean(axis=0).max() < 0.5  # nem vertical
    assert tinta.sum() > 0.2 * (np.asarray(imagem) < 128).sum()  # o texto continua lá


@tesseract
def test_ocr_le_tabela_com_grade():
    texto = " ".join(p.texto for p in ler_imagem(_tabela(dpi=146), 146))  # como no memorial
    verdade = " ".join(f"{r} {v}" for r, v in QUADRO)
    assert cer(texto, verdade) < 0.05


@tesseract
def test_ocr_le_pagina_com_borda_decorativa():
    """Papel de segurança de certidões: faixas com desenho nas margens (docs/06 §5)."""
    imagem, _ = _pagina()
    largura, altura = imagem.size
    com_borda = Image.new("L", (largura + 240, altura), 255)
    com_borda.paste(imagem, (120, 0))
    d = ImageDraw.Draw(com_borda)
    for x0 in (10, largura + 130):  # faixa ondulada em cada margem
        for y in range(0, altura, 6):
            d.line((x0, y, x0 + 100, y + 40), fill=90, width=1)
            d.line((x0 + 100, y, x0, y + 40), fill=90, width=1)
    palavras = ler_imagem(com_borda, 200)
    texto = " ".join(p.texto for p in palavras if p.confianca >= 0.5)
    assert cer(texto, " ".join(LINHAS)) < 0.08


def test_separar_erros_distingue_texto_errado_de_texto_a_mais():
    verdade = "MATRÍCULA Nº 71.677 área de 400,00 m²"
    assert separar_erros(verdade, verdade) == (0, 0)
    # carimbo lido a mais no fim: só "texto a mais"
    assert separar_erros(verdade + " CÓPIA", verdade) == (0, 6)
    # um caractere trocado: erro no texto verdadeiro
    assert separar_erros(verdade.replace("400", "4O0"), verdade) == (1, 0)
    # palavra perdida: erro no texto verdadeiro
    assert separar_erros(verdade.replace(" m²", ""), verdade) == (3, 0)
