"""Testes da montagem da base sintética (conjuntos + gabaritos)."""

import json

import pymupdf
import pytest

from arquiteto_auditor.avaliacao.gabarito import carregar_gabarito
from dados_sinteticos.geradores.gerar_base import CONJUNTOS, gerar_conjunto, montar_projeto


def test_base_tem_ao_menos_seis_conjuntos_variados():
    assert len(CONJUNTOS) >= 6
    projetos = [montar_projeto(d) for d in CONJUNTOS]
    assert {p.variacao.estilo_carimbo for p in projetos} == {0, 1, 2, 3}
    assert {p.variacao.estilo_quadro for p in projetos} == {0, 1, 2, 3}
    assert {p.variacao.formato for p in projetos} == {"A1", "A2", "A3"}


def test_base_tem_conjunto_limpo_e_conjuntos_reservados():
    assert any(not d.erros for d in CONJUNTOS)
    assert sum(d.reservado for d in CONJUNTOS) >= 2


def test_base_cobre_os_tipos_de_erro_do_gabarito_real():
    erros = {e.split(":")[0] for d in CONJUNTOS for e in d.erros}
    assert {"area_terreno_divergente", "cota_omitida", "sem_assinatura_autor",
            "sem_assinatura_proprietario", "assinatura_alterada", "sem_proprietario",
            "muro_alto", "sem_norte"} <= erros


def test_identificadores_unicos():
    nomes = [d.conjunto for d in CONJUNTOS]
    assert len(nomes) == len(set(nomes))


@pytest.mark.parametrize("definicao", CONJUNTOS, ids=lambda d: d.conjunto)
def test_gabarito_tem_um_erro_por_erro_injetado(definicao):
    from dados_sinteticos.geradores.especificacao import gerar_gabarito

    gabarito = gerar_gabarito(montar_projeto(definicao), definicao.conjunto)
    assert len(gabarito.erros_esperados()) == len(definicao.erros)


def test_gerar_conjunto_grava_pdfs_assinados_gabarito_e_especificacao(tmp_path):
    definicao = CONJUNTOS[0]
    pasta = gerar_conjunto(definicao, tmp_path)
    gabarito = carregar_gabarito(pasta / "gabarito.json")
    assert gabarito.conjunto == definicao.conjunto
    especificacao = json.loads((pasta / "especificacao.json").read_text(encoding="utf-8"))
    assert especificacao["semente"] == definicao.semente
    pdfs = sorted(pasta.glob("*.pdf"))
    assert pdfs
    for pdf in pdfs:
        documento = pymupdf.open(pdf)
        assert documento.is_pdf
        assert any(w.field_type_string == "Signature" for p in documento for w in p.widgets())
