"""Testes da lei municipal e da norma do condomínio fictícias."""

import pymupdf
import pytest

from dados_sinteticos.geradores.desenho import formatar_numero
from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.legislacao import (
    CAMPOS_LEI,
    ZONAS,
    ZONAS_RESIDENCIAIS,
    gerar_lei,
    gerar_norma_condominio,
    gerar_norma_escaneada,
    gerar_pdf_normativo,
)

SEMENTES = range(101, 109)


def _texto(documento) -> str:
    pdf = pymupdf.open(stream=gerar_pdf_normativo(documento))
    return " ".join(" ".join(pagina.get_text().split()) for pagina in pdf)


@pytest.mark.parametrize("semente", SEMENTES)
def test_zona_do_projeto_tem_os_parametros_da_prefeitura(semente):
    projeto = gerar_projeto_base(semente)
    lei = gerar_lei(projeto)
    assert lei.zona in ZONAS_RESIDENCIAIS
    for campo, _, _ in CAMPOS_LEI:
        assert lei.parametros_por_zona[lei.zona][campo] == getattr(projeto.prefeitura, campo)


@pytest.mark.parametrize("semente", SEMENTES)
def test_outras_zonas_residenciais_tem_valores_diferentes(semente):
    lei = gerar_lei(gerar_projeto_base(semente))
    proprios = lei.parametros_por_zona[lei.zona]
    for zona in ZONAS_RESIDENCIAIS:
        if zona != lei.zona:
            diferentes = sum(lei.parametros_por_zona[zona][c] != proprios[c]
                             for c, _, _ in CAMPOS_LEI)
            assert diferentes >= 3, zona


@pytest.mark.parametrize("semente", [101, 102])
def test_lei_identifica_a_zona_pelo_condominio_e_tem_volume(semente):
    projeto = gerar_projeto_base(semente)
    lei = gerar_lei(projeto)
    pdf = pymupdf.open(stream=gerar_pdf_normativo(lei.documento))
    assert pdf.page_count >= 20
    anexo_i = [b.texto for b in lei.documento.blocos
               if b.tipo == "artigo" and "compreende as áreas" in b.texto]
    assert len(anexo_i) == len(ZONAS)
    com_condominio = [t for t in anexo_i if projeto.identificacao.condominio in t]
    assert len(com_condominio) == 1 and com_condominio[0].startswith(lei.zona)
    texto = " ".join(" ".join(p.get_text().split()) for p in pdf)
    assert "DOCUMENTO FICTÍCIO" in texto
    assert "relação percentual entre a área de projeção da edificação e a área do lote" in texto


def test_modelos_a_e_b_e_armadilha_da_redacao_anterior():
    leis = {lei.modelo: lei for lei in (gerar_lei(gerar_projeto_base(s)) for s in SEMENTES)}
    assert set(leis) == {"A", "B"}
    assert leis["A"].valor_antigo is None
    b = leis["B"]
    campo, antigo = b.valor_antigo
    atual = b.parametros_por_zona[b.zona][campo]
    assert antigo != atual
    texto = " ".join(blc.texto for blc in b.documento.blocos)
    assert f"recuo frontal mínimo será de {formatar_numero(atual)} m" in texto
    assert f"Redação anterior: \"Na {b.zona}, o recuo frontal mínimo será de " \
           f"{formatar_numero(antigo)} m.\"" in texto


@pytest.mark.parametrize("semente", SEMENTES)
def test_norma_traz_os_parametros_do_condominio(semente):
    projeto = gerar_projeto_base(semente)
    c = projeto.condominio
    texto = _texto(gerar_norma_condominio(projeto).documento)
    assert f"altura máxima de {formatar_numero(c.muro_altura_max)} m" in texto
    if c.to_max is not None:
        assert f"taxa de ocupação máxima de cada lote é de {int(c.to_max)}%" in texto
    else:
        assert "taxa de ocupação máxima" not in texto
    assert "legislação municipal, que prevalece" in texto  # hierarquia declarada na norma


def test_base_tem_conflito_entre_condominio_e_prefeitura():
    conflitos = 0
    for semente in SEMENTES:
        p = gerar_projeto_base(semente)
        if p.condominio.to_max is not None and p.condominio.to_max != p.prefeitura.to_max:
            conflitos += 1
    assert conflitos >= 2


def test_norma_escaneada_so_tem_imagem():
    norma = gerar_norma_condominio(gerar_projeto_base(103))
    doc = gerar_norma_escaneada(norma.documento, "media", 1)
    pdf = pymupdf.open(stream=doc.pdf)
    assert pdf.page_count == len(doc.texto_por_pagina) >= 2
    assert all(not p.get_text().strip() for p in pdf)
    assert "REGULAMENTO DE OBRAS" in doc.texto_por_pagina[0]
