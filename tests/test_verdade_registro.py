"""Testes da verdade da matrícula e da escritura sintéticas (base da Fase 7)."""

import json
from pathlib import Path

import pytest

from arquiteto_auditor.avaliacao.verdade_registro import verdade_do_registro
from arquiteto_auditor.dominio.registro import TipoAto

PASTA = Path(__file__).resolve().parent.parent / "dados_sinteticos" / "projetos"
CONJUNTOS = sorted(p.name for p in PASTA.iterdir() if p.is_dir())


def _verdade(conjunto: str):
    return verdade_do_registro(json.loads(
        (PASTA / conjunto / "especificacao.json").read_text(encoding="utf-8")))


def test_atos_e_estado_atual_da_matricula():
    v = _verdade("sint-006")
    assert [(a.codigo, a.tipo, a.data) for a in v.atos] == [
        ("R-1", TipoAto.COMPRA_E_VENDA, "21/03/2010"),
        ("AV-2", TipoAto.RETIFICACAO, "08/09/2010"),
        ("R-3", TipoAto.ALIENACAO_FIDUCIARIA, "21/12/2011"),
        ("AV-4", TipoAto.CANCELAMENTO, "27/08/2012"),
        ("AV-5", TipoAto.ALTERACAO_DENOMINACAO, "17/03/2013"),
        ("R-6", TipoAto.COMPRA_E_VENDA, "20/04/2014"),
    ]
    assert v.area_atual == 450.0 and v.proprietario_atual == "Valentim Azevedo Correia"
    assert v.onus_ativos == []
    assert v.escritura_area == 450.0 and v.escritura_data == "13/04/2013"


@pytest.mark.parametrize("conjunto", CONJUNTOS)
def test_todo_conjunto_tem_verdade_registral(conjunto):
    v = _verdade(conjunto)
    assert v.atos and v.atos[0].codigo == "R-1" and v.area_atual > 0 and v.proprietario_atual
