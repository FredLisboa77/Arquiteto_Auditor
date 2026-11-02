"""Testes do motor de verificação (Fase 9): cada regra, inclusive valores exatamente no limite."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    OrigemValor,
    StatusConfirmacao,
    StatusItem,
    ValorExtraido,
)
from arquiteto_auditor.dominio.numeros import casas_decimais, formatar_numero
from arquiteto_auditor.dominio.parametros import ParametroAdotado
from arquiteto_auditor.verificacao.formulas import calcular_indice, formulas
from arquiteto_auditor.verificacao.regras import (
    REGRAS_DE_LIMITE,
    verificar_declarado,
    verificar_limite,
    verificar_soma,
)


def _valor(campo, valor, trecho=None, pendente=False, documento="pranchas.pdf"):
    return ValorExtraido(
        campo=campo, valor=valor, origem=OrigemValor.VETORIAL, confianca=0.95,
        evidencias=[Evidencia(documento=documento, pagina=1,
                              trecho=trecho or f"{campo}: {formatar_numero(valor)}")],
        status=StatusConfirmacao.PENDENTE if pendente else StatusConfirmacao.AUTOMATICO)


def _parametro(chave, valor, fonte="prefeitura", pendente=False, observacao=None):
    return ParametroAdotado(chave, _valor(chave, valor, documento="lei.pdf", pendente=pendente),
                            fonte, observacao=observacao)


# ------------------------------------------------------------------ formatação


def test_formatar_numero_brasileiro():
    assert formatar_numero(1234.5) == "1.234,50"
    assert formatar_numero(8.0, 1) == "8,0"
    assert formatar_numero(-0.004) == "0,00"
    assert formatar_numero(2, 0) == "2"


def test_casas_decimais_como_escritas():
    assert casas_decimais("TAXA DE OCUPAÇÃO: 35,23%", 35.23) == 2
    assert casas_decimais("TO 35,2%", 35.2) == 1
    assert casas_decimais("recuo 5.00 m", 5.0) == 2
    assert casas_decimais("CA 1", 1) == 0
    assert casas_decimais("sem o número", 3) is None


# ------------------------------------------------------------------ fórmulas


def test_formulas_padrao():
    assert set(formulas()) == {"TO", "CA", "PERMEAVEL"}
    assert formulas()["TO"].numerador == "AREA_PROJECAO"


def test_indice_calculado_exato_e_rastreavel():
    to = calcular_indice("TO", _valor("AREA_PROJECAO", 240.0), _valor("TERRENO_AREA", 400.0),
                         "TO_PROJETO")
    assert to.valor == 60.0  # exato, sem 60,000…01
    assert to.origem == "calculado" and to.calculado_de == ["AREA_PROJECAO", "TERRENO_AREA"]
    assert len(to.evidencias) == 2 and "240,00 ÷ 400,00" in to.observacao
    ca = calcular_indice("CA", _valor("AREA_CONSTR_TOTAL", 226.8), _valor("TERRENO_AREA", 360),
                         "CA_PROJETO")
    assert ca.valor == pytest.approx(0.63) and ca.unidade is None


def test_indice_sem_dados_ou_com_pendencia():
    assert calcular_indice("TO", None, _valor("TERRENO_AREA", 400), "X") is None
    assert calcular_indice("TO", _valor("AREA_PROJECAO", 10), _valor("TERRENO_AREA", 0),
                           "X") is None
    to = calcular_indice("TO", _valor("AREA_PROJECAO", 100),
                         _valor("TERRENO_AREA", 400, pendente=True), "X")
    assert to.status == StatusConfirmacao.PENDENTE


# ------------------------------------------------------------------ projeto × parâmetro


def _limite(chave, valor_projeto, limite, **kw):
    projeto = _valor("PROJETO", valor_projeto, pendente=kw.pop("pendente_projeto", False))
    return verificar_limite(chave, projeto, _parametro(chave, limite, **kw))


@pytest.mark.parametrize("chave", sorted(REGRAS_DE_LIMITE))
def test_cada_regra_no_limite_atende_e_fora_nao_atende(chave):
    regra = REGRAS_DE_LIMITE[chave]
    limite = 4.0 if chave == "PAVIMENTOS_MAX" else 5.0
    passo = 1.0 if chave == "PAVIMENTOS_MAX" else 0.01
    no_limite = _limite(chave, limite, limite)
    assert no_limite.status == StatusItem.ATENDE
    assert no_limite.margem == 0 and "no limite" in no_limite.mensagem
    assert no_limite.sugestao is None

    pior = limite + passo if regra.limite == "maximo" else limite - passo
    fora = _limite(chave, pior, limite)
    assert fora.status == StatusItem.NAO_ATENDE
    assert fora.margem == pytest.approx(-passo)
    assert fora.sugestao

    melhor = limite - passo if regra.limite == "maximo" else limite + passo
    assert _limite(chave, melhor, limite).margem == pytest.approx(passo)


def test_exemplo_do_criterio_de_aceite_to():
    """TO 62% / 60% num terreno de 400 m² → reduzir 8,0 m² de projeção."""
    projecao, area = _valor("AREA_PROJECAO", 248.0), _valor("TERRENO_AREA", 400.0)
    to = calcular_indice("TO", projecao, area, "TO_PROJETO")
    item = verificar_limite("TO_MAX", to, _parametro("TO_MAX", 60.0), area_terreno=area,
                            numerador=projecao)
    assert item.status == StatusItem.NAO_ATENDE
    assert item.valor_projeto == 62.0 and item.limite == 60.0 and item.margem == -2.0
    assert "excede 2,00 p.p." in item.mensagem
    assert "reduzir ≈ 8,00 m² de projeção" in item.sugestao
    assert "para no máximo 240,00 m²" in item.sugestao
    assert any("Fórmula padrão" in o for o in item.observacoes)
    assert len(item.evidencias) == 3  # projeção, área do terreno e parâmetro


def test_quantidades_sugeridas():
    area = _valor("TERRENO_AREA", 360.0)
    ca = verificar_limite("CA_MAX", calcular_indice("CA", _valor("AREA_CONSTR_TOTAL", 400.0),
                                                    area, "CA_PROJETO"),
                          _parametro("CA_MAX", 1.0), area_terreno=area,
                          numerador=_valor("AREA_CONSTR_TOTAL", 400.0))
    assert "reduzir ≈ 40,00 m² de área construída computável" in ca.sugestao

    permeavel = _valor("AREA_PERMEAVEL", 54.0)
    tp = verificar_limite("PERMEAVEL_MIN", calcular_indice("PERMEAVEL", permeavel, area, "TP"),
                          _parametro("PERMEAVEL_MIN", 20.0), area_terreno=area,
                          numerador=permeavel)
    assert tp.status == StatusItem.NAO_ATENDE
    assert "aumentar ≈ 18,00 m² de área permeável" in tp.sugestao  # 72 − 54

    assert "Aumentar o recuo em 0,50 m" in _limite("RECUO_FRONTAL", 4.5, 5.0).sugestao
    assert "Reduzir a altura do muro em 0,40 m" in _limite("MURO_ALTURA_MAX", 2.4, 2.0).sugestao
    assert "Reduzir 1 pavimento(s)" in _limite("PAVIMENTOS_MAX", 3, 2).sugestao


def test_sem_parametro_ou_sem_projeto_nao_e_verificavel():
    sem_parametro = verificar_limite("ALTURA_MAX", _valor("ALTURA", 7.0), None)
    assert sem_parametro.status == StatusItem.NAO_VERIFICAVEL
    assert "informe o parâmetro" in sem_parametro.mensagem

    sem_projeto = verificar_limite("RECUO_FUNDOS", None, _parametro("RECUO_FUNDOS", 2.0),
                                   sem_projeto="Cota do recuo de fundos não indicada.")
    assert sem_projeto.status == StatusItem.NAO_VERIFICAVEL
    assert sem_projeto.mensagem == "Cota do recuo de fundos não indicada."
    assert sem_projeto.limite == 2.0


def test_conflito_e_pendencia_aparecem_no_item():
    obs = "A norma do condomínio define 35; vale o da prefeitura, que prevalece."
    item = _limite("TO_MAX", 30.0, 40.0, observacao=obs)
    assert obs in item.observacoes and "(prefeitura)" in item.mensagem
    assert not item.baixa_confianca
    assert _limite("TO_MAX", 30.0, 40.0, pendente=True).baixa_confianca
    assert _limite("TO_MAX", 30.0, 40.0, pendente_projeto=True).baixa_confianca
    assert "(condomínio)" in _limite("MURO_ALTURA_MAX", 2.0, 2.2, fonte="condominio").mensagem


# ------------------------------------------------------------------ declarado × recalculado


def _recalculado(valor):
    return ValorExtraido(campo="TO_PROJETO", valor=valor, origem=OrigemValor.CALCULADO,
                         confianca=0.9, calculado_de=["AREA_PROJECAO", "TERRENO_AREA"],
                         evidencias=[Evidencia(documento="p.pdf", pagina=1, trecho="x")])


@pytest.mark.parametrize("declarado, trecho, recalculado, status", [
    (35.23, "TAXA DE OCUPAÇÃO: 35,23%", 35.2251, StatusItem.ATENDE),  # arredondamento
    (35.23, "TAXA DE OCUPAÇÃO: 35,23%", 35.235, StatusItem.ATENDE),  # meia unidade: limite
    (35.23, "TAXA DE OCUPAÇÃO: 35,23%", 35.2401, StatusItem.DIVERGENTE),
    (35.2, "TAXA DE OCUPAÇÃO: 35,2%", 35.24, StatusItem.ATENDE),  # 1 casa: tolera 0,05
    (35.0, "TAXA DE OCUPAÇÃO: 35,00%", 35.23, StatusItem.DIVERGENTE),
])
def test_indice_declarado_com_arredondamento(declarado, trecho, recalculado, status):
    item = verificar_declarado("TO_DECLARADA", "taxa de ocupação",
                               _valor("TO_DECLARADA", declarado, trecho), _recalculado(recalculado),
                               0.005, "%")
    assert item.status == status
    assert bool(item.sugestao) == (status == StatusItem.DIVERGENTE)


def test_declarado_sem_dados():
    item = verificar_declarado("CA_DECLARADO", "coeficiente de aproveitamento", None,
                               _recalculado(0.5), 0.005)
    assert item.status == StatusItem.NAO_VERIFICAVEL


def test_soma_dos_pavimentos():
    parciais = [_valor("AREA_CONSTR_PAV_1", 126.0), _valor("AREA_CONSTR_PAV_2", 100.8)]
    assert verificar_soma(parciais, _valor("AREA_CONSTR_TOTAL", 226.8), 0.01).status == "atende"
    assert verificar_soma(parciais, _valor("AREA_CONSTR_TOTAL", 226.81), 0.01).status == "atende"
    errada = verificar_soma(parciais, _valor("AREA_CONSTR_TOTAL", 236.8), 0.01)
    assert errada.status == StatusItem.DIVERGENTE and "diferença de 10,00 m²" in errada.mensagem
    assert verificar_soma([], None, 0.01).status == StatusItem.NAO_VERIFICAVEL


# ------------------------------------------------------------------ sem LLM no motor

PASTA_MOTOR = Path(__file__).resolve().parents[1] / "src" / "arquiteto_auditor" / "verificacao"
PROIBIDOS = ("arquiteto_auditor.llm", "arquiteto_auditor.extracao", "urllib", "http", "socket",
             "ollama", "requests", "httpx")


def test_motor_nao_importa_llm_nem_rede():
    """Nenhum arquivo do motor importa o LLM, a extração (que usa o LLM) ou rede."""
    arquivos = sorted(PASTA_MOTOR.glob("*.py"))
    assert arquivos
    for arquivo in arquivos:
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            nomes = ([a.name for a in no.names] if isinstance(no, ast.Import)
                     else [no.module or ""] if isinstance(no, ast.ImportFrom) else [])
            for nome in nomes:
                assert not nome.startswith(PROIBIDOS), f"{arquivo.name} importa {nome}"


def test_carregar_o_motor_nao_carrega_o_llm():
    codigo = ("import sys, importlib, pkgutil, arquiteto_auditor.verificacao as v\n"
              "[importlib.import_module(f'{v.__name__}.{m.name}') "
              "for m in pkgutil.iter_modules(v.__path__)]\n"
              "print([m for m in sys.modules if m.startswith('arquiteto_auditor.llm')])")
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                           check=True)
    assert saida.stdout.strip() == "[]"
