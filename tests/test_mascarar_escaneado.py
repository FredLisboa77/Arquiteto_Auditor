"""Testes da calibração com escaneados (estatísticas e máscara), usando páginas sintéticas."""

import random

import numpy as np
import pytest
from PIL import Image

from dados_sinteticos.geradores.escaneado import QUALIDADES, Estilo, renderizar
from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.registro import gerar_matricula, paginas_da_matricula
from scripts.mascarar_escaneado import (
    analisar_pagina,
    estimar_inclinacao,
    luminancia,
    quadricular,
)

DPI = 150


@pytest.fixture(scope="module")
def pagina_sintetica() -> np.ndarray:
    paginas = paginas_da_matricula(gerar_matricula(gerar_projeto_base(102)), semente=1,
                                   estilo="ficha")
    paginas[0].rubricas_apos = None  # só tinta preta
    imagem = renderizar(paginas[0], QUALIDADES["ruim"], random.Random(1))  # 150 dpi
    return np.asarray(imagem, dtype=np.float64)


def _girar(rgb: np.ndarray, angulo: float) -> np.ndarray:
    imagem = Image.fromarray(rgb.astype(np.uint8))
    girada = imagem.rotate(angulo, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    return np.asarray(girada, dtype=np.float64)


def test_quadricular_ignora_blocos_com_pouca_tinta():
    mascara = np.zeros((4, 4), bool)
    mascara[0, 0] = True  # 1 de 4 pixels no bloco de cima à esquerda (25%)
    mascara[2:4, 2:4] = True  # bloco de baixo à direita cheio
    resultado = quadricular(mascara, 2, 2, densidade=0.3)
    assert not resultado[:2, :2].any()
    assert resultado[2:, 2:].all()
    assert quadricular(mascara, 2, 2)[:2, :2].all()  # densidade 0: qualquer pixel basta


@pytest.mark.parametrize("angulo", [-2.5, -1.0, 0.0, 1.5, 3.0])
def test_inclinacao_estimada(pagina_sintetica, angulo):
    tinta = luminancia(_girar(pagina_sintetica, angulo)) < 150
    assert estimar_inclinacao(tinta[::2, ::2]) == pytest.approx(angulo, abs=0.3)


def test_estatisticas_da_pagina_sintetica(pagina_sintetica):
    analise = analisar_pagina(_girar(pagina_sintetica, 1.0), DPI)
    texto = "\n".join(analise.linhas)
    entrelinha_mm = Estilo().entrelinha_pt * 25.4 / 72
    medida = float(texto.split("entrelinha: mediana ")[1].split(" mm")[0])
    assert medida == pytest.approx(entrelinha_mm, abs=0.3)
    justificadas = int(texto.split("alinhamento à direita: ")[1].split("%")[0])
    assert justificadas >= 50  # a matrícula sintética é justificada
    assert "inclinação estimada: +1.0°" in texto


def test_mascara_nao_preserva_os_tracos_originais(pagina_sintetica):
    analise = analisar_pagina(pagina_sintetica, DPI)
    mascarada = np.asarray(analise.mascarada.convert("L"), dtype=np.float64)
    # só sobram dois "tons": papel (claro, com ruído) e barras (cinza 95); nada de letras
    escuros = mascarada[mascarada < 200]
    assert escuros.size > 0
    assert np.all(escuros == 95)
    assert analise.mascarada.width == round(pagina_sintetica.shape[1] * 100 / DPI)
