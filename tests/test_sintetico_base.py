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
    assert gabarito.zona == especificacao["legislacao"]["zona"]
    for nome in ("lei_municipal.pdf", "norma_condominio.pdf"):
        assert "DOCUMENTO FICTÍCIO" in " ".join(p.get_text() for p in pymupdf.open(pasta / nome))
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


# ---------------------------------------------------------------- revisões R00 → R01


def _definicao(nome):
    return next(d for d in CONJUNTOS if d.conjunto == nome)


def test_comparar_rodadas_classifica_cada_situacao():
    from arquiteto_auditor.avaliacao.gabarito import Gabarito
    from dados_sinteticos.geradores.especificacao import comparar_rodadas

    def gabarito(rodada, itens, anterior=None):
        return Gabarito.model_validate({
            "conjunto": f"x-{rodada.lower()}", "versao_gabarito": 1, "rodada": rodada,
            "conjunto_anterior": anterior,
            "itens_esperados": [{"chave": c, "status": s} for c, s in itens]})

    r00 = gabarito("R00", [("ID_MATRICULA", "divergente"), ("TO_MAX", "nao_atende"),
                           ("ALTURA_MAX", "atende"), ("NORTE_INDICADO", "atende"),
                           ("RECUO_FRONTAL", "atende")])
    r01 = gabarito("R01", [("ID_MATRICULA", "atende"), ("TO_MAX", "nao_atende"),
                           ("ALTURA_MAX", "nao_verificavel"), ("NORTE_INDICADO", "nao_atende"),
                           ("RECUO_FRONTAL", "atende")], anterior="x-r00")
    assert comparar_rodadas(r00, r01) == [
        {"chave": "ID_MATRICULA", "resultado": "resolvido"},
        {"chave": "TO_MAX", "resultado": "pendente"},
        {"chave": "ALTURA_MAX", "resultado": "nao_verificavel_agora"},
        {"chave": "NORTE_INDICADO", "resultado": "novo"},
    ]


def test_r01_e_o_mesmo_projeto_que_r00_com_parte_dos_erros_corrigida():
    r00, r01 = _definicao("sint-009"), _definicao("sint-010")
    assert r01.rodada == "R01" and r01.conjunto_anterior == r00.conjunto
    p00, p01 = montar_projeto(r00), montar_projeto(r01)
    for campo in ("matricula", "lote", "quadra", "condominio", "titulo", "municipio"):
        assert getattr(p00.identificacao, campo) == getattr(p01.identificacao, campo)
    assert (p00.identificacao.revisao, p01.identificacao.revisao) == ("R00", "R01")
    corrigidos = set(r00.erros) - set(r01.erros)
    mantidos = set(r00.erros) & set(r01.erros)
    novos = set(r01.erros) - set(r00.erros)
    assert corrigidos and mantidos and len(novos) == 1


def test_gabarito_da_r01_traz_todos_os_resultados_de_comparacao():
    from dados_sinteticos.geradores.gerar_base import gerar_gabarito_do_conjunto

    gabarito = gerar_gabarito_do_conjunto(_definicao("sint-010"))
    resultados = {c.resultado.value for c in gabarito.comparacao_rodada_anterior}
    assert resultados == {"resolvido", "pendente", "novo", "nao_verificavel_agora"}
    assert gabarito.conjunto_anterior == "sint-009" and gabarito.rodada == "R01"


def test_documentos_nao_assinados_tem_bytes_reprodutiveis():
    """Regerar a base não deve mudar arquivos cujo conteúdo não mudou (histórico do Git)."""
    from dados_sinteticos.geradores.especificacao import gerar_projeto_base
    from dados_sinteticos.geradores.legislacao import gerar_lei, gerar_pdf_normativo
    from dados_sinteticos.geradores.memorial import gerar_memorial, gerar_memorial_pdf
    from dados_sinteticos.geradores.registro import gerar_matricula_escaneada

    projeto = gerar_projeto_base(101)

    def gerar():
        return (gerar_pdf_normativo(gerar_lei(projeto).documento),
                gerar_memorial_pdf(gerar_memorial(projeto)),
                gerar_matricula_escaneada(projeto, "ruim")[1].pdf)

    assert gerar() == gerar()
