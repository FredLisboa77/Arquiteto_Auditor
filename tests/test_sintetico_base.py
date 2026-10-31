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
    pranchas = sorted(pasta.glob("prancha*.pdf"))
    assert pranchas
    for pdf in pranchas:
        documento = pymupdf.open(pdf)
        assert documento.is_pdf
        assert any(w.field_type_string == "Signature" for p in documento for w in p.widgets())

    # documentos registrais escaneados + verdade do OCR
    verdade = json.loads((pasta / "verdade_ocr.json").read_text(encoding="utf-8"))
    for nome in ("matricula.pdf", "escritura.pdf"):
        documento = pymupdf.open(pasta / nome)
        assert documento.page_count == len(verdade[nome])
        assert all(not p.get_text().strip() for p in documento)  # só imagem
    memorial = pymupdf.open(pasta / "memorial.pdf")  # conjunto 1: memorial digitado e assinado
    assert "MEMORIAL DESCRITIVO" in memorial[0].get_text()
    assert any(w.field_type_string == "Signature" for p in memorial for w in p.widgets())
    registrais = especificacao["documentos_registrais"]
    assert gabarito.valores_esperados["TERRENO_AREA"]["matricula"] == (
        registrais["matricula"]["area_atual"])
    assert gabarito.valores_esperados["TERRENO_AREA"]["escritura"] == (
        registrais["escritura"]["area_descrita"])
    assert gabarito.valores_esperados["ID_PROPRIETARIO"]["matricula"] == (
        especificacao["identificacao"]["proprietario"])


def test_base_tem_memorial_em_texto_e_escaneado():
    formas = [d.memorial for d in CONJUNTOS]
    assert "texto" in formas
    assert {"boa", "media", "ruim"} <= set(formas)


def test_base_varia_estilo_e_qualidade_dos_escaneados():
    assert {d.matricula[0] for d in CONJUNTOS} == {"ficha", "certidao"}
    qualidades = {d.matricula[1] for d in CONJUNTOS} | {d.escritura for d in CONJUNTOS}
    assert qualidades == {"boa", "media", "ruim"}
    # o caso típico (escaneamento de mesa limpo) é a maioria
    assert sum(d.escritura == "boa" for d in CONJUNTOS) >= len(CONJUNTOS) // 2
