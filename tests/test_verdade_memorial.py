"""Testes da verdade do memorial sintético (o que cada estilo mostra)."""

import json
from pathlib import Path

import pytest

from arquiteto_auditor.avaliacao.verdade_memorial import CAMPOS_MEMORIAL, verdade_do_memorial

PASTA = Path(__file__).resolve().parent.parent / "dados_sinteticos" / "projetos"


def _verdade(conjunto: str):
    especificacao = json.loads((PASTA / conjunto / "especificacao.json").read_text(
        encoding="utf-8"))
    ocr = json.loads((PASTA / conjunto / "verdade_ocr.json").read_text(encoding="utf-8"))
    return verdade_do_memorial(especificacao, narrativo=any("imagem" in k for k in ocr))


def test_memorial_estruturado_mostra_recuos_e_profundidade():
    v = _verdade("sint-003")  # recuo de fundos e altura omitidos
    assert set(v) == set(CAMPOS_MEMORIAL)
    assert v["RECUO_FUNDOS"] is None and v["ALTURA"] is None
    assert v["TERRENO_PROFUNDIDADE"] == 35.0 and v["RECUO_FRONTAL"] == 5.5
    assert v["RRT"] and v["MATRICULA"]


def test_memorial_narrativo_nao_mostra_recuos_nem_matricula():
    v = _verdade("sint-015")
    assert v["RECUO_FRONTAL"] is None and v["MATRICULA"] is None and v["RRT"] is None
    assert v["AREA_CONSTR_TOTAL"] is not None and v["AUTOR"]


def test_area_total_divergente_do_memorial():
    e = json.loads((PASTA / "sint-009" / "especificacao.json").read_text(encoding="utf-8"))
    assert _verdade("sint-009")["AREA_CONSTR_TOTAL"] == e["apresentacao"]["area_total_memorial"]


@pytest.mark.parametrize("conjunto", sorted(p.name for p in PASTA.iterdir() if p.is_dir()))
def test_todo_conjunto_tem_verdade_do_memorial(conjunto):
    assert _verdade(conjunto)["TERRENO_AREA"] > 0
