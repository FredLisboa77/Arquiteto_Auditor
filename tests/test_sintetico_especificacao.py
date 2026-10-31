"""Testes da especificação dos projetos sintéticos (a "verdade" de onde saem PDFs e gabarito)."""

import pytest

from arquiteto_auditor.avaliacao.gabarito import Gabarito
from dados_sinteticos.geradores.especificacao import (
    ERROS_DISPONIVEIS,
    aplicar_erros,
    gerar_gabarito,
    gerar_projeto_base,
)


def status(gabarito: Gabarito) -> dict:
    return {(i.chave, i.escopo): i.status.value for i in gabarito.itens_esperados}


@pytest.mark.parametrize("semente", range(20))
def test_projeto_base_atende_todos_os_parametros(semente):
    projeto = gerar_projeto_base(semente)
    gabarito = gerar_gabarito(projeto, conjunto="sint-teste")
    assert gabarito.erros_esperados() == []


def test_projeto_base_e_deterministico():
    assert gerar_projeto_base(7) == gerar_projeto_base(7)
    assert gerar_projeto_base(7) != gerar_projeto_base(8)


def test_projeto_base_tem_identificacao_ficticia_completa():
    ident = gerar_projeto_base(1).identificacao
    for campo in ("titulo", "autor", "registro_autor", "rrt", "revisao", "endereco", "lote",
                  "quadra", "condominio", "matricula", "cartorio", "proprietario"):
        assert getattr(ident, campo), campo


@pytest.mark.parametrize("semente", range(50))
def test_cpf_do_proprietario_e_sempre_invalido(semente):
    from scripts.verificar_vazamento import cpf_valido

    cpf = gerar_projeto_base(semente).identificacao.cpf_proprietario
    digitos = cpf.replace(".", "").replace("-", "")
    assert len(digitos) == 11
    assert not cpf_valido(digitos)


def test_geometria_fecha():
    p = gerar_projeto_base(3)
    e, t = p.edificacao, p.terreno
    assert e.recuo_lateral_e + e.largura + p.recuo_lateral_d == pytest.approx(t.testada)
    assert e.recuo_frontal + e.profundidade + p.recuo_fundos == pytest.approx(t.profundidade)


def test_gabarito_gerado_e_valido_e_cobre_as_chaves_principais():
    gabarito = gerar_gabarito(gerar_projeto_base(2), conjunto="sint-teste")
    chaves = {i.chave for i in gabarito.itens_esperados}
    assert {"TERRENO_AREA", "TO_MAX", "RECUO_FRONTAL", "NORTE_INDICADO",
            "ASSINATURA_DIGITAL_VALIDA", "MURO_ALTURA_MAX"} <= chaves


def test_hierarquia_prefeitura_prevalece_sobre_condominio():
    projeto = gerar_projeto_base(4)
    projeto.prefeitura.to_max = 60.0
    projeto.condominio.to_max = 50.0
    assert projeto.parametro_adotado("to_max") == 60.0
    projeto.prefeitura.muro_altura_max = None
    projeto.condominio.muro_altura_max = 1.8
    assert projeto.parametro_adotado("muro_altura_max") == 1.8


# ---------------------------------------------------------------- injeção de erros


@pytest.mark.parametrize(
    ("erro", "chave", "escopo", "esperado"),
    [
        ("area_terreno_divergente", "TERRENO_AREA", None, "divergente"),
        ("soma_areas_errada", "AREA_CONSTR_SOMA", None, "divergente"),
        ("to_declarada_errada", "TO_DECLARADA", None, "divergente"),
        ("to_excedida", "TO_MAX", None, "nao_atende"),
        ("recuo_frontal_insuficiente", "RECUO_FRONTAL", None, "nao_atende"),
        ("matricula_divergente", "ID_MATRICULA", None, "divergente"),
        ("revisao_divergente", "ID_REVISAO", None, "divergente"),
        ("cota_omitida:recuo_fundos", "COTA_INDEFINIDA", "elemento=recuo_fundos", "nao_atende"),
        ("sem_norte", "NORTE_INDICADO", None, "nao_atende"),
        ("sem_proprietario", "ID_PROPRIETARIO", None, "nao_atende"),
        ("sem_assinatura_autor", "ASSINATURA_AUTOR", None, "nao_atende"),
        ("sem_assinatura_proprietario", "ASSINATURA_PROPRIETARIO", None, "nao_atende"),
        ("assinatura_alterada", "ASSINATURA_DIGITAL_VALIDA", None, "nao_atende"),
        ("muro_alto", "MURO_ALTURA_MAX", None, "nao_atende"),
        ("altura_excedida", "ALTURA_MAX", None, "nao_atende"),
    ],
)
def test_cada_erro_gera_o_item_esperado_no_gabarito(erro, chave, escopo, esperado):
    projeto = aplicar_erros(gerar_projeto_base(5), [erro])
    gabarito = gerar_gabarito(projeto, conjunto="sint-teste")
    assert status(gabarito)[(chave, escopo)] == esperado


@pytest.mark.parametrize("semente", range(30))
def test_cada_erro_afeta_so_o_proprio_item(semente):
    for erro in ERROS_DISPONIVEIS:
        if erro == "cota_omitida":
            erro = "cota_omitida:recuo_fundos"
        projeto = aplicar_erros(gerar_projeto_base(semente), [erro])
        erros = gerar_gabarito(projeto, conjunto="sint-teste").erros_esperados()
        assert len(erros) == 1, (erro, [e.chave for e in erros])


def test_erro_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="erro desconhecido"):
        aplicar_erros(gerar_projeto_base(1), ["erro_inventado"])


def test_to_excedida_informa_valor_e_limite():
    projeto = aplicar_erros(gerar_projeto_base(5), ["to_excedida"])
    item = next(i for i in gerar_gabarito(projeto, "sint-teste").itens_esperados
                if i.chave == "TO_MAX")
    assert item.valor_projeto > item.limite
