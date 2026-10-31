"""Testes das classes de domínio: as regras de evidência e confiança valem para todo o sistema."""

import pytest
from pydantic import ValidationError

from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    ItemVerificacao,
    OrigemValor,
    Parametro,
    Rodada,
    StatusConfirmacao,
    StatusItem,
    ValorExtraido,
)


def evidencia(**alteracoes):
    dados = {"documento": "prancha_01.pdf", "pagina": 1, "trecho": "ÁREA DO TERRENO: 450,00 m²"}
    return Evidencia(**(dados | alteracoes))


# ---------------------------------------------------------------- Evidencia


def test_evidencia_minima():
    e = evidencia()
    assert e.pagina == 1
    assert e.bbox is None


def test_evidencia_exige_pagina_a_partir_de_1():
    with pytest.raises(ValidationError):
        evidencia(pagina=0)


def test_evidencia_exige_trecho():
    with pytest.raises(ValidationError):
        evidencia(trecho="   ")


def test_evidencia_rejeita_bbox_invertida():
    with pytest.raises(ValidationError):
        evidencia(bbox=(100, 100, 50, 120))


# ---------------------------------------------------------------- ValorExtraido


def test_valor_vetorial_exige_evidencia():
    with pytest.raises(ValidationError):
        ValorExtraido(campo="TERRENO_AREA", valor=450.0, origem=OrigemValor.VETORIAL,
                      confianca=0.95, evidencias=[])


def test_valor_com_evidencia():
    v = ValorExtraido(campo="TERRENO_AREA", valor=450.0, unidade="m2",
                      origem=OrigemValor.VETORIAL, confianca=0.95, evidencias=[evidencia()])
    assert v.status == StatusConfirmacao.AUTOMATICO


def test_confianca_entre_0_e_1():
    with pytest.raises(ValidationError):
        ValorExtraido(campo="X", valor=1.0, origem=OrigemValor.OCR, confianca=1.5,
                      evidencias=[evidencia()])


def test_valor_calculado_exige_origem_do_calculo():
    with pytest.raises(ValidationError):
        ValorExtraido(campo="TO", valor=62.0, origem=OrigemValor.CALCULADO, confianca=1.0)
    v = ValorExtraido(campo="TO", valor=62.0, origem=OrigemValor.CALCULADO, confianca=1.0,
                      calculado_de=["AREA_PROJECAO", "TERRENO_AREA"])
    assert v.calculado_de


def test_valor_informado_pelo_revisor_exige_observacao():
    with pytest.raises(ValidationError):
        ValorExtraido(campo="RECUO_FRONTAL", valor=5.0, origem=OrigemValor.REVISOR, confianca=1.0)
    v = ValorExtraido(campo="RECUO_FRONTAL", valor=5.0, origem=OrigemValor.REVISOR,
                      confianca=1.0, observacao="Cota conferida na prancha 02")
    assert v.observacao


@pytest.mark.parametrize(("confianca", "esperado"), [(0.59, True), (0.6, False), (0.99, False)])
def test_precisa_confirmacao_abaixo_do_limiar(confianca, esperado):
    v = ValorExtraido(campo="X", valor=1.0, origem=OrigemValor.OCR, confianca=confianca,
                      evidencias=[evidencia()])
    assert v.precisa_confirmacao(limiar=0.6) is esperado


def test_valor_confirmado_nao_precisa_mais_de_confirmacao():
    v = ValorExtraido(campo="X", valor=1.0, origem=OrigemValor.OCR, confianca=0.3,
                      evidencias=[evidencia()], status=StatusConfirmacao.CONFIRMADO)
    assert not v.precisa_confirmacao(limiar=0.6)


# ---------------------------------------------------------------- Parametro


def test_parametro_exige_evidencia_da_lei():
    with pytest.raises(ValidationError):
        Parametro(chave="TO_MAX", valor=60.0, unidade="%", fonte="prefeitura",
                  limite="maximo", confianca=0.9, evidencias=[])


def test_parametro_valido():
    p = Parametro(chave="TO_MAX", valor=60.0, unidade="%", fonte="prefeitura", limite="maximo",
                  zona="ZR-2", confianca=0.9,
                  evidencias=[evidencia(documento="lei.pdf", pagina=34, trecho="TO máxima: 60%")])
    assert p.fonte == "prefeitura"


# ---------------------------------------------------------------- ItemVerificacao


def test_item_conclusivo_exige_evidencia():
    for status in (StatusItem.ATENDE, StatusItem.NAO_ATENDE, StatusItem.DIVERGENTE):
        with pytest.raises(ValidationError):
            ItemVerificacao(chave="TO_MAX", status=status, mensagem="x", evidencias=[])


def test_item_nao_verificavel_pode_nao_ter_evidencia_mas_exige_motivo():
    item = ItemVerificacao(chave="ALTURA_MAX", status=StatusItem.NAO_VERIFICAVEL,
                           mensagem="Altura não encontrada nos cortes")
    assert item.evidencias == []
    with pytest.raises(ValidationError):
        ItemVerificacao(chave="ALTURA_MAX", status=StatusItem.NAO_VERIFICAVEL, mensagem=" ")


def test_chave_estavel_inclui_escopo():
    item = ItemVerificacao(chave="AREA_CONSTR_PAV", escopo="pavimento=1",
                           status=StatusItem.ATENDE, mensagem="ok", evidencias=[evidencia()])
    assert item.chave_estavel == ("AREA_CONSTR_PAV", "pavimento=1")


def test_chave_em_formato_maiusculo():
    with pytest.raises(ValidationError):
        ItemVerificacao(chave="to_max", status=StatusItem.NAO_VERIFICAVEL, mensagem="x")


# ---------------------------------------------------------------- Rodada


@pytest.mark.parametrize("codigo", ["R00", "R01", "R12"])
def test_codigo_de_rodada_valido(codigo):
    assert Rodada(codigo=codigo).codigo == codigo


@pytest.mark.parametrize("codigo", ["R0", "r01", "R001", "REV1", ""])
def test_codigo_de_rodada_invalido(codigo):
    with pytest.raises(ValidationError):
        Rodada(codigo=codigo)


def test_proxima_rodada():
    assert Rodada(codigo="R00").proximo_codigo() == "R01"
    assert Rodada(codigo="R09").proximo_codigo() == "R10"
