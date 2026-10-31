"""Testes das variações calibradas com memorial, código de obras e normas reais (docs/06 §6)."""

import dataclasses

import pymupdf
import pytest

from dados_sinteticos.geradores.desenho import formatar_numero as n
from dados_sinteticos.geradores.escaneado import QUALIDADES, escanear_pdf
from dados_sinteticos.geradores.especificacao import gerar_gabarito, gerar_projeto_base
from dados_sinteticos.geradores.gerar_base import CONJUNTOS, montar_projeto
from dados_sinteticos.geradores.legislacao import (
    ZONAS,
    gerar_lei,
    gerar_norma_condominio,
    gerar_pdf_normativo,
    metros_por_extenso,
)
from dados_sinteticos.geradores.memorial import gerar_memorial_narrativo
from dados_sinteticos.geradores.pranchas import AMBIENTES_TERREO, area_util

CONDOMINIO = {"area_construida_min": 100.0, "recuo_frontal_min": 3.0, "recuo_fundos_min": 1.5,
              "recuo_lateral_min": 1.5, "to_max": 60.0, "permeavel_min": 20.0,
              "altura_max": 10.0, "pavimentos_max": 2}


def _projeto(semente=114, **condominio):
    projeto = gerar_projeto_base(semente)
    projeto.condominio = dataclasses.replace(projeto.condominio, **(CONDOMINIO | condominio))
    return projeto


def _texto(pdf: bytes) -> str:
    return " ".join(" ".join(p.get_text().split()) for p in pymupdf.open(stream=pdf))


# ---------------------------------------------------------------- cópia escaneada


def test_copia_escaneada_de_um_pdf_de_texto():
    pdf = gerar_pdf_normativo(gerar_lei(_projeto(), "C").documento)
    doc = escanear_pdf(pdf, "copia", 1)
    original, copia = pymupdf.open(stream=pdf), pymupdf.open(stream=doc.pdf)
    assert copia.page_count == original.page_count == len(doc.texto_por_pagina)
    assert all(not p.get_text().strip() for p in copia)
    assert " ".join(original[0].get_text().split()) == " ".join(doc.texto_por_pagina[0].split())
    resolucoes = set()
    for pagina in copia:
        imagem = copia.extract_image(pagina.get_images()[0][0])
        resolucoes.add(round(imagem["width"] / (pagina.rect.width / 72)))
    assert QUALIDADES["copia"].dpi in resolucoes and 200 in resolucoes  # páginas refeitas
    assert len(doc.pdf) < 4.5 * 1024 * 1024


# ---------------------------------------------------------------- lei modelo C


@pytest.mark.parametrize("semente", [114, 115, 116, 117])
def test_lei_c_valores_por_faixa_de_area_e_celulas_mescladas(semente):
    projeto = _projeto(semente)
    lei = gerar_lei(projeto, "C")
    tabela = next(b for b in lei.documento.blocos if b.mescladas)
    assert len(tabela.mescladas) == len(ZONAS)
    acima = projeto.terreno.area > lei.limiar_area
    coluna = 3 if acima else 2
    linhas_da_zona = _linhas_da_zona(tabela.linhas, lei.zona)
    recuo = next(linha for linha in linhas_da_zona if linha[1].startswith("Recuo frontal"))
    esperado = n(projeto.prefeitura.recuo_frontal_min)
    assert recuo[coluna] == esperado
    assert recuo[5 - coluna] != esperado  # a outra faixa é distração
    assert lei.documento.timbre and "PREFEITURA" in lei.documento.timbre[0]


def _linhas_da_zona(linhas, zona):
    """Linhas da tabela que pertencem à zona (a célula da zona só aparece na 1ª linha)."""
    resultado, dentro = [], False
    for linha in linhas[1:]:
        if linha[0]:
            dentro = linha[0] == zona
        if dentro:
            resultado.append(linha)
    return resultado


# ---------------------------------------------------------------- norma numerada


def test_metros_por_extenso():
    assert metros_por_extenso(3.0) == "três metros"
    assert metros_por_extenso(1.5) == "um metro e meio"
    assert metros_por_extenso(2.2) == "dois metros e vinte centímetros"
    assert metros_por_extenso(0.8) == "oitenta centímetros"


def test_norma_numerada_tem_ponto_decimal_extenso_e_muro_por_posicao():
    projeto = _projeto()
    texto = _texto(gerar_pdf_normativo(gerar_norma_condominio(projeto, "numerada").documento))
    muro = projeto.condominio.muro_altura_max
    assert "Recuo Frontal: mínimo de 3.00 m (três metros)" in texto
    assert f"Fundo do lote: muro de {muro:.2f} m ({metros_por_extenso(muro)})" in texto
    assert "Frente do lote: não poderá ser construído muro" in texto
    assert "80 cm (oitenta centímetros)" in texto and "45°" in texto
    assert "100.00 m² (cem metros quadrados)" in texto
    assert "2.50 m" in texto  # muro do condomínio: distração
    assert "60% (sessenta por cento)" in texto


def test_area_construida_minima_so_entra_quando_definida():
    com = gerar_gabarito(_projeto(), "x")
    item = next(i for i in com.itens_esperados if i.chave == "AREA_CONSTR_MIN")
    assert item.status == "atende" and com.valores_esperados["AREA_CONSTR_MIN"]["condominio"] == 100
    sem = gerar_gabarito(gerar_projeto_base(114), "x")
    assert all(i.chave != "AREA_CONSTR_MIN" for i in sem.itens_esperados)


@pytest.mark.parametrize("conjunto", ["sint-014", "sint-015", "sint-016"])
def test_erros_violam_a_prefeitura_mas_nao_o_condominio(conjunto):
    """Testa a hierarquia: quem aplicasse o limite do condomínio deixaria passar o erro."""
    definicao = next(d for d in CONJUNTOS if d.conjunto == conjunto)
    projeto = montar_projeto(definicao)
    gabarito = gerar_gabarito(projeto, conjunto)
    so_prefeitura = 0
    for item in gabarito.erros_esperados():
        valores = gabarito.valores_esperados.get(item.chave, {})
        if "prefeitura" in valores and "condominio" in valores:
            limite_condominio, valor = valores["condominio"], valores["calculado"]
            minimo = item.chave.startswith("RECUO")
            atende_condominio = valor >= limite_condominio if minimo else valor <= limite_condominio
            so_prefeitura += atende_condominio
    assert so_prefeitura >= 1


# ---------------------------------------------------------------- memorial narrativo


def test_memorial_narrativo_tem_quadro_so_como_imagem():
    projeto = _projeto()
    memorial = gerar_memorial_narrativo(projeto)
    pdf = pymupdf.open(stream=memorial.pdf)
    assert pdf.page_count == 1 and len(pdf[0].get_images()) == 1
    texto = _texto(memorial.pdf)
    area_terreno = f"{n(projeto.area_terreno_prancha)} m²"
    assert area_terreno not in texto  # só no quadro, que é imagem
    assert f"Área do terreno {area_terreno}" in memorial.texto_da_imagem
    assert f"área construída total de {n(projeto.area_total_memorial)}m²" in texto
    # as áreas dos ambientes são as mesmas das plantas
    garagem = next(a for a in AMBIENTES_TERREO if a[0] == "Garagem")
    assert f"Garagem ({n(area_util(projeto.edificacao, garagem))}m²)" in texto
