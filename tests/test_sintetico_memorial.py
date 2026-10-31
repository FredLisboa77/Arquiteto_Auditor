"""Testes do memorial descritivo fictício (espelha as pranchas; versões texto e escaneada)."""

import pymupdf
import pytest

from dados_sinteticos.geradores.desenho import formatar_numero as n
from dados_sinteticos.geradores.especificacao import (
    aplicar_erros,
    gerar_gabarito,
    gerar_projeto_base,
)
from dados_sinteticos.geradores.memorial import (
    gerar_memorial,
    gerar_memorial_escaneado,
    gerar_memorial_pdf,
    paginas_do_memorial,
)


def _texto_pdf(projeto) -> str:
    documento = pymupdf.open(stream=gerar_memorial_pdf(gerar_memorial(projeto)))
    return " ".join(" ".join(p.get_text().split()) for p in documento)


@pytest.mark.parametrize("semente", range(101, 107))
def test_memorial_mostra_os_valores_da_prancha(semente):
    p = gerar_projeto_base(semente)
    texto = _texto_pdf(p)
    for trecho in (f"{n(p.area_terreno_prancha)} m²", f"{n(p.area_total_prancha)} m²",
                   f"{n(p.to_prancha)} %", n(p.ca_prancha), f"{n(p.tp_prancha)} %",
                   p.matricula_prancha, p.identificacao.autor, p.identificacao.registro_autor,
                   p.identificacao.rrt, p.identificacao.proprietario,
                   f"{n(p.edificacao.recuo_frontal)} m", f"{n(p.edificacao.altura)} m"):
        assert trecho in texto, trecho
    assert "DOCUMENTO FICTÍCIO" in texto


def test_memorial_repete_os_erros_da_prancha():
    p = aplicar_erros(gerar_projeto_base(102), ["area_terreno_divergente",
                                                "matricula_divergente"])
    texto = _texto_pdf(p)
    assert f"{n(p.area_terreno_prancha)} m²" in texto
    assert f"{n(p.terreno.area)} m²" not in texto  # a verdade fica só na matrícula
    assert p.matricula_prancha in texto and p.identificacao.matricula not in texto


def test_memorial_omite_o_que_a_prancha_omite():
    p = aplicar_erros(gerar_projeto_base(103), [
        "cota_omitida:recuo_fundos", "cota_omitida:altura_total", "cota_omitida:testada",
        "sem_proprietario"])
    texto = _texto_pdf(p)
    assert "Recuo de fundos" not in texto
    assert "altura total" not in texto.lower()
    assert "testada" not in texto
    assert p.identificacao.proprietario not in texto
    assert "Recuo frontal" in texto  # o resto continua


def test_erro_memorial_area_divergente():
    p = aplicar_erros(gerar_projeto_base(104), ["memorial_area_divergente"])
    assert p.area_total_memorial != p.area_total_prancha
    texto = _texto_pdf(p)
    assert f"{n(p.area_total_memorial)} m²" in texto
    gabarito = gerar_gabarito(p, "teste")
    item = next(i for i in gabarito.itens_esperados if i.chave == "AREA_CONSTR_TOTAL")
    assert item.status == "divergente" and item.documentos == ["prancha", "memorial"]
    assert len(gabarito.erros_esperados()) == 1


def test_memorial_texto_tem_texto_selecionavel_e_negrito():
    documento = pymupdf.open(stream=gerar_memorial_pdf(gerar_memorial(gerar_projeto_base(101))))
    fontes = {s["font"] for b in documento[0].get_text("dict")["blocks"]
              for linha in b.get("lines", []) for s in linha["spans"]}
    assert any("Bold" in f for f in fontes) and any("Bold" not in f for f in fontes)
    assert "ESPECIFICAÇÕES TÉCNICAS" in " ".join(p.get_text() for p in documento)


def test_memorial_escaneado_assina_como_as_pranchas():
    p = aplicar_erros(gerar_projeto_base(105), ["sem_assinatura_autor"])
    paginas = paginas_do_memorial(gerar_memorial(p))
    linhas_assinatura = [linha for pg in paginas for linha in pg.linhas
                         if linha.texto.startswith("___")]
    assert [linha.assinar for linha in linhas_assinatura] == [False, True]  # autor, proprietário


def test_memorial_escaneado_so_tem_imagem():
    doc = gerar_memorial_escaneado(gerar_memorial(gerar_projeto_base(106)), "media", 1)
    pdf = pymupdf.open(stream=doc.pdf)
    assert pdf.page_count == len(doc.texto_por_pagina)
    assert all(not pagina.get_text().strip() for pagina in pdf)
    assert "MEMORIAL DESCRITIVO" in doc.texto_por_pagina[0]
