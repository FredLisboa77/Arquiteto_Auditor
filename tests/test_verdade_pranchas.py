"""Testes da verdade das pranchas sintéticas (o que cada prancha mostra), base da Fase 6."""

import json
from pathlib import Path

import pytest

from arquiteto_auditor.avaliacao.verdade_pranchas import CAMPOS, verdade_das_pranchas

PASTA = Path(__file__).resolve().parent.parent / "dados_sinteticos" / "projetos"


def _especificacao(conjunto: str) -> dict:
    return json.loads((PASTA / conjunto / "especificacao.json").read_text(encoding="utf-8"))


def test_conjunto_limpo_mostra_a_verdade_do_projeto():
    v = verdade_das_pranchas(_especificacao("sint-001"))
    assert set(v) == set(CAMPOS)
    assert v["TERRENO_AREA"] == 400.0
    assert v["TERRENO_TESTADA"] == 12.5
    assert v["AREA_CONSTR_PAV_1"] == 119.97 and v["AREA_CONSTR_PAV_2"] == 95.98
    assert v["AREA_CONSTR_TOTAL"] == 215.95
    assert v["TO_DECLARADA"] == 29.99 and v["CA_DECLARADO"] == 0.54
    assert v["PERMEAVEL_DECLARADA"] == 28.0
    assert v["RECUO_FRONTAL"] == 6.0 and v["RECUO_LATERAL_D"] == 1.5
    assert v["RECUO_FUNDOS"] == 13.03
    assert v["ALTURA"] == 6.5 and v["MURO_ALTURA"] == 1.8
    assert v["MATRICULA"] == "71.677" and v["REVISAO"] == "R00"
    assert v["PROPRIETARIO"] == "Milena Cunha Pereira"


def test_erros_injetados_mudam_o_que_a_prancha_mostra():
    v = verdade_das_pranchas(_especificacao("sint-003"))  # cotas omitidas
    assert v["RECUO_FUNDOS"] is None and v["ALTURA"] is None
    assert verdade_das_pranchas(_especificacao("sint-004"))["PROPRIETARIO"] is None
    e = _especificacao("sint-002")  # área do terreno e matrícula divergentes
    v = verdade_das_pranchas(e)
    assert v["TERRENO_AREA"] == e["apresentacao"]["area_terreno"]
    assert v["MATRICULA"] == e["apresentacao"]["matricula"]


@pytest.mark.parametrize("conjunto", sorted(p.name for p in PASTA.iterdir() if p.is_dir()))
def test_todo_conjunto_tem_verdade(conjunto):
    v = verdade_das_pranchas(_especificacao(conjunto))
    assert v["AREA_CONSTR_TOTAL"] > 0 and v["TITULO"]


@pytest.mark.parametrize("conjunto", sorted(p.name for p in PASTA.iterdir() if p.is_dir()))
def test_verdade_concorda_com_o_gabarito(conjunto):
    v = verdade_das_pranchas(_especificacao(conjunto))
    esperados = json.loads((PASTA / conjunto / "gabarito.json").read_text(
        encoding="utf-8"))["valores_esperados"]
    assert v["TERRENO_AREA"] == esperados["TERRENO_AREA"]["prancha"]
    assert v["AREA_CONSTR_TOTAL"] == esperados["AREA_CONSTR_TOTAL"]["prancha"]
    for campo in ("RECUO_FRONTAL", "RECUO_LATERAL_E", "RECUO_LATERAL_D", "RECUO_FUNDOS"):
        if v[campo] is not None and campo in esperados:
            assert v[campo] == esperados[campo]["calculado"], campo
