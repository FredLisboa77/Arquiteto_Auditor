"""O que as pranchas de um conjunto sintético MOSTRAM: a verdade para medir a extração (Fase 6).

Sai da especificacao.json gravada pelo gerador (dados_sinteticos/geradores/especificacao.py),
seguindo as mesmas regras de lá: os erros injetados mudam o que a prancha mostra (ex.: área do
terreno divergente) e as cotas omitidas não aparecem (valor None = a prancha não mostra).

Os nomes dos campos são os da extração (ValorExtraido.campo), não as chaves dos itens de
verificação: um campo vira dado de um ou mais itens (ex.: AREA_CONSTR_PAV_1 → AREA_CONSTR_PAV).
"""

from __future__ import annotations

CAMPOS_IDENTIFICACAO = (
    "TITULO", "ENDERECO", "CONDOMINIO", "LOTE", "QUADRA", "MUNICIPIO", "MATRICULA", "CARTORIO",
    "PROPRIETARIO", "AUTOR", "AUTOR_REGISTRO", "RRT", "REVISAO",
)
CAMPOS_NUMERICOS = (
    "TERRENO_AREA", "TERRENO_TESTADA", "TERRENO_PROFUNDIDADE", "AREA_CONSTR_PAV_1",
    "AREA_CONSTR_PAV_2", "AREA_CONSTR_TOTAL", "AREA_PROJECAO", "AREA_PERMEAVEL", "TO_DECLARADA",
    "CA_DECLARADO", "PERMEAVEL_DECLARADA", "RECUO_FRONTAL", "RECUO_LATERAL_E", "RECUO_LATERAL_D",
    "RECUO_FUNDOS", "ALTURA", "MURO_ALTURA",
)
CAMPOS = CAMPOS_IDENTIFICACAO + CAMPOS_NUMERICOS


def verdade_das_pranchas(especificacao: dict) -> dict[str, float | str | None]:
    ident, terreno = especificacao["identificacao"], especificacao["terreno"]
    edif, apres = especificacao["edificacao"], especificacao["apresentacao"]
    omitidas = set(apres["cotas_omitidas"])

    def cota(elemento: str, valor: float) -> float | None:
        return None if elemento in omitidas else round(valor, 2)

    area_terreno = apres["area_terreno"] or round(terreno["testada"] * terreno["profundidade"], 2)
    pavimentos = edif["areas_pavimentos"]
    area_total = apres["area_total"] or round(sum(pavimentos), 2)
    projecao = round(edif["largura"] * edif["profundidade"], 2)
    to = apres["to_declarada"]
    if to is None:
        to = round(projecao / area_terreno * 100, 2)
    revisao = apres["revisao_por_folha"].get("0", ident["revisao"])

    return {
        "TITULO": ident["titulo"],
        "ENDERECO": ident["endereco"],
        "CONDOMINIO": ident["condominio"],
        "LOTE": ident["lote"],
        "QUADRA": ident["quadra"],
        "MUNICIPIO": ident["municipio"],
        "MATRICULA": apres["matricula"] or ident["matricula"],
        "CARTORIO": ident["cartorio"],
        "PROPRIETARIO": ident["proprietario"] if apres["mostrar_proprietario"] else None,
        "AUTOR": ident["autor"],
        "AUTOR_REGISTRO": ident["registro_autor"],
        "RRT": ident["rrt"],
        "REVISAO": None if especificacao["variacao"]["revisao_em_branco"] else revisao,
        "TERRENO_AREA": area_terreno,
        "TERRENO_TESTADA": cota("testada", terreno["testada"]),
        "TERRENO_PROFUNDIDADE": cota("profundidade_lote", terreno["profundidade"]),
        "AREA_CONSTR_PAV_1": pavimentos[0],
        "AREA_CONSTR_PAV_2": pavimentos[1] if len(pavimentos) > 1 else None,
        "AREA_CONSTR_TOTAL": area_total,
        "AREA_PROJECAO": projecao,
        "AREA_PERMEAVEL": edif["area_permeavel"],
        "TO_DECLARADA": to,
        "CA_DECLARADO": round(area_total / area_terreno, 2),
        "PERMEAVEL_DECLARADA": round(edif["area_permeavel"] / area_terreno * 100, 2),
        "RECUO_FRONTAL": cota("recuo_frontal", edif["recuo_frontal"]),
        "RECUO_LATERAL_E": cota("recuo_lateral_e", edif["recuo_lateral_e"]),
        "RECUO_LATERAL_D": cota("recuo_lateral_d", terreno["testada"] - edif["recuo_lateral_e"]
                                - edif["largura"]),
        "RECUO_FUNDOS": cota("recuo_fundos", terreno["profundidade"] - edif["recuo_frontal"]
                             - edif["profundidade"]),
        "ALTURA": cota("altura_total", edif["altura"]),
        "MURO_ALTURA": cota("muro", edif["muro_altura"]),
    }
