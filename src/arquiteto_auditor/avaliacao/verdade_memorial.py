"""O que o memorial descritivo sintético MOSTRA: a verdade para medir a leitura (Fase 7).

O memorial é do autor e repete os valores das pranchas, inclusive os erros e as omissões
injetados (dados_sinteticos/geradores/memorial.py). Diferenças:
- a área total pode divergir do quadro das pranchas (erro "memorial_area_divergente");
- a profundidade do lote aparece sempre no texto sobre o terreno;
- o estilo NARRATIVO (1 página, quadro de áreas como imagem) não traz matrícula, RRT,
  testada, profundidade, recuos nem muro.
None = o memorial não mostra (nada deve ser extraído).
"""

from __future__ import annotations

from arquiteto_auditor.avaliacao.verdade_pranchas import verdade_das_pranchas

CAMPOS_IDENTIFICACAO_MEMORIAL = ("MATRICULA", "PROPRIETARIO", "AUTOR", "AUTOR_REGISTRO", "RRT")
CAMPOS_NUMERICOS_MEMORIAL = (
    "TERRENO_AREA", "TERRENO_TESTADA", "TERRENO_PROFUNDIDADE", "AREA_CONSTR_PAV_1",
    "AREA_CONSTR_PAV_2", "AREA_CONSTR_TOTAL", "AREA_PROJECAO", "AREA_PERMEAVEL", "TO_DECLARADA",
    "CA_DECLARADO", "PERMEAVEL_DECLARADA", "RECUO_FRONTAL", "RECUO_LATERAL_E", "RECUO_LATERAL_D",
    "RECUO_FUNDOS", "ALTURA", "MURO_ALTURA",
)
CAMPOS_MEMORIAL = CAMPOS_IDENTIFICACAO_MEMORIAL + CAMPOS_NUMERICOS_MEMORIAL
_SO_NO_ESTRUTURADO = ("MATRICULA", "RRT", "TERRENO_TESTADA", "TERRENO_PROFUNDIDADE",
                      "RECUO_FRONTAL", "RECUO_LATERAL_E", "RECUO_LATERAL_D", "RECUO_FUNDOS",
                      "MURO_ALTURA")


def verdade_do_memorial(especificacao: dict, narrativo: bool) -> dict[str, float | str | None]:
    pranchas = verdade_das_pranchas(especificacao)
    verdade = {campo: pranchas[campo] for campo in CAMPOS_MEMORIAL}
    total = especificacao["apresentacao"]["area_total_memorial"]
    if total is not None:
        verdade["AREA_CONSTR_TOTAL"] = total
    verdade["TERRENO_PROFUNDIDADE"] = especificacao["terreno"]["profundidade"]
    if narrativo:
        for campo in _SO_NO_ESTRUTURADO:
            verdade[campo] = None
    return verdade
