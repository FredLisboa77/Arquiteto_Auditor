"""Testes do catálogo de verificações (chaves estáveis usadas no versionamento R00 → R01)."""

import pytest

from arquiteto_auditor.dominio.catalogo import CatalogoInvalido, carregar_catalogo

# Chaves que obrigatoriamente existem (docs/02-mvp.md §4 e §4.1, e o gabarito real).
CHAVES_OBRIGATORIAS = {
    "ID_MATRICULA", "ID_CARTORIO", "ID_LOTE_QUADRA", "ID_CONDOMINIO", "ID_ENDERECO",
    "ID_AUTOR_REGISTRO", "ID_RRT_ART", "ID_REVISAO", "ID_PROPRIETARIO",
    "TERRENO_AREA", "TERRENO_TESTADA", "AREA_CONSTR_PAV", "AREA_CONSTR_TOTAL",
    "AREA_CONSTR_SOMA", "LOTE_AREA_MIN", "LOTE_TESTADA_MIN",
    "RECUO_FRONTAL", "RECUO_LATERAL_E", "RECUO_LATERAL_D", "RECUO_FUNDOS",
    "TO_MAX", "TO_DECLARADA", "CA_MAX", "CA_DECLARADO", "PERMEAVEL_MIN", "PERMEAVEL_DECLARADA",
    "ALTURA_MAX", "PAVIMENTOS_MAX", "MURO_ALTURA_MAX",
    "COTA_INDEFINIDA", "NORTE_INDICADO",
    "ASSINATURA_AUTOR", "ASSINATURA_PROPRIETARIO", "ASSINATURA_DIGITAL_VALIDA",
}


def test_catalogo_padrao_carrega_e_tem_as_chaves_obrigatorias():
    catalogo = carregar_catalogo()
    assert CHAVES_OBRIGATORIAS <= set(catalogo)


def test_cada_definicao_tem_nome_tipo_e_descricao():
    for chave, definicao in carregar_catalogo().items():
        assert definicao.chave == chave
        assert definicao.nome
        assert definicao.descricao
        assert definicao.tipo in {
            "identificacao", "consistencia", "parametro", "aritmetica", "completude",
        }


def test_chaves_com_escopo():
    catalogo = carregar_catalogo()
    assert catalogo["AREA_CONSTR_PAV"].escopo == "pavimento"
    assert catalogo["COTA_INDEFINIDA"].escopo == "elemento"
    assert catalogo["TO_MAX"].escopo is None


def escrever(tmp_path, conteudo):
    arquivo = tmp_path / "catalogo.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_rejeita_chave_duplicada(tmp_path):
    item = '[[verificacao]]\nchave="TO_MAX"\nnome="a"\ntipo="parametro"\ndescricao="b"\n'
    with pytest.raises(CatalogoInvalido, match="duplicada"):
        carregar_catalogo(escrever(tmp_path, item + item))


def test_rejeita_chave_fora_do_padrao(tmp_path):
    item = '[[verificacao]]\nchave="to max"\nnome="a"\ntipo="parametro"\ndescricao="b"\n'
    with pytest.raises(CatalogoInvalido, match="to max"):
        carregar_catalogo(escrever(tmp_path, item))


def test_rejeita_tipo_desconhecido(tmp_path):
    item = '[[verificacao]]\nchave="X"\nnome="a"\ntipo="juridico"\ndescricao="b"\n'
    with pytest.raises(CatalogoInvalido):
        carregar_catalogo(escrever(tmp_path, item))
