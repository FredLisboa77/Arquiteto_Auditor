"""Cálculo dos índices urbanísticos (TO, CA, permeabilidade) pelas fórmulas de formulas.toml.

Código determinístico: o LLM nunca calcula (CLAUDE.md §3). O resultado é um ValorExtraido
de origem "calculado", com os campos usados, as evidências deles e a fórmula na observação
(o relatório sempre diz qual fórmula foi usada).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from arquiteto_auditor.dominio.modelos import OrigemValor, StatusConfirmacao, ValorExtraido
from arquiteto_auditor.dominio.numeros import formatar_numero

ARQUIVO = Path(__file__).with_name("formulas.toml")


@dataclass(frozen=True)
class Formula:
    codigo: str  # "TO", "CA", "PERMEAVEL"
    nome: str
    numerador: str  # campo do projeto
    fator: float
    descricao: str
    exclusoes: str


@cache
def formulas() -> dict[str, Formula]:
    dados = tomllib.loads(ARQUIVO.read_text(encoding="utf-8"))
    return {codigo: Formula(codigo=codigo, nome=f["nome"], numerador=f["numerador"],
                            fator=float(f["fator"]), descricao=f["descricao"],
                            exclusoes=f["exclusoes"])
            for codigo, f in dados.items()}


def calcular_indice(codigo: str, numerador: ValorExtraido | None,
                    area_terreno: ValorExtraido | None, campo: str) -> ValorExtraido | None:
    """O índice do projeto; None se falta um dos valores (ou a área do terreno é zero)."""
    formula = formulas()[codigo]
    if numerador is None or area_terreno is None or float(area_terreno.valor) <= 0:
        return None
    # Multiplicar antes de dividir: 240 × 100 ÷ 400 dá 60 exato (0,6 × 100 daria 60,000…01).
    valor = float(numerador.valor) * formula.fator / float(area_terreno.valor)
    pendente = StatusConfirmacao.PENDENTE in (numerador.status, area_terreno.status)
    origem_area = area_terreno.evidencias[0].documento if area_terreno.evidencias else "?"
    return ValorExtraido(
        campo=campo, valor=valor, unidade="%" if formula.fator == 100 else None,
        origem=OrigemValor.CALCULADO,
        confianca=min(numerador.confianca, area_terreno.confianca),
        evidencias=[*numerador.evidencias, *area_terreno.evidencias],
        status=StatusConfirmacao.PENDENTE if pendente else StatusConfirmacao.AUTOMATICO,
        calculado_de=[numerador.campo, area_terreno.campo],
        observacao=(f"{formula.descricao} = {formatar_numero(float(numerador.valor))} ÷ "
                    f"{formatar_numero(float(area_terreno.valor))} m² ({origem_area}). "
                    f"Fórmula padrão (formulas.toml): {formula.exclusoes}."))
