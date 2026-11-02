"""Testes do recorte da evidência (imagem do trecho de onde saiu um valor)."""

import io

import numpy as np
import pymupdf
from PIL import Image

from arquiteto_auditor.dominio.modelos import Evidencia
from arquiteto_auditor.extracao.recorte import recortar_evidencia


def _pdf(tmp_path):
    caminho = tmp_path / "prancha.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page(width=842, height=595)
    pagina.insert_text((400, 300), "RECUO FRONTAL 6,00", fontsize=10)
    documento.save(caminho)
    original = caminho.read_bytes()
    return caminho, original


def test_recorte_mostra_o_trecho_com_margem_e_destaque(tmp_path):
    caminho, original = _pdf(tmp_path)
    evidencia = Evidencia(documento="prancha.pdf", pagina=1, trecho="RECUO FRONTAL 6,00",
                          bbox=(400, 290, 500, 302))
    imagem = Image.open(io.BytesIO(recortar_evidencia(caminho, evidencia, margem=20, dpi=144,
                                                       minimo=(0, 0))))
    assert imagem.format == "PNG"
    assert abs(imagem.width - (100 + 40) * 2) <= 2 and abs(imagem.height - (12 + 40) * 2) <= 2
    pixels = np.asarray(imagem.convert("RGB")).astype(int)
    assert (pixels.sum(axis=2) < 200).any()  # o texto aparece
    vermelho = (pixels[..., 0] > 180) & (pixels[..., 1] < 80) & (pixels[..., 2] < 80)
    assert vermelho.any()  # o trecho está destacado
    assert caminho.read_bytes() == original  # o documento de entrada não muda (CLAUDE.md §3)


def test_recorte_perto_da_borda_fica_dentro_da_pagina(tmp_path):
    caminho, _ = _pdf(tmp_path)
    evidencia = Evidencia(documento="prancha.pdf", pagina=1, trecho="x", bbox=(0, 0, 30, 10))
    imagem = Image.open(io.BytesIO(recortar_evidencia(caminho, evidencia, margem=20, dpi=72,
                                                       minimo=(0, 0))))
    assert imagem.width == 50 and imagem.height == 30


def test_evidencia_sem_bbox_recorta_a_pagina_inteira(tmp_path):
    caminho, _ = _pdf(tmp_path)
    evidencia = Evidencia(documento="prancha.pdf", pagina=1, trecho="x")
    imagem = Image.open(io.BytesIO(recortar_evidencia(caminho, evidencia, dpi=36)))
    assert (imagem.width, imagem.height) == (421, 298)


def test_recorte_de_trecho_pequeno_mostra_o_contexto_em_volta(tmp_path):
    caminho, _ = _pdf(tmp_path)
    evidencia = Evidencia(documento="prancha.pdf", pagina=1, trecho="2.00",
                          bbox=(400, 300, 415, 308))
    imagem = Image.open(io.BytesIO(recortar_evidencia(caminho, evidencia, dpi=72,
                                                      minimo=(240, 160))))
    assert abs(imagem.width - 240) <= 1 and abs(imagem.height - 160) <= 1  # arredondamento
