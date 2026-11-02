"""Motor de verificação: de tudo o que foi lido (Fatos) para os itens do catálogo.

Código determinístico, sem LLM e sem leitura de documentos: recebe os valores já extraídos
(pranchas, memorial, matrícula, escritura), os parâmetros adotados e as constatações de
completude, e devolve um ItemVerificacao por chave do catálogo (e por escopo).

De onde vem cada valor do PROJETO:
- recuos, altura, muro, projeção e áreas: das pranchas (o desenho é o projeto); se a prancha
  não traz o valor (ou a leitura falhou), vale o do memorial, com baixa confiança e a origem
  na observação;
- área do terreno usada nos índices e no lote mínimo: a do estado atual da matrícula; na
  falta, a da escritura, da prancha ou do memorial (nessa ordem);
- aritmética (soma dos pavimentos, índices declarados × recalculados): o quadro de áreas da
  prancha, com a área do terreno da própria prancha; o memorial só na falta do quadro (um
  erro no total do memorial já aparece em "área construída total");
- área do terreno entre documentos: com a matrícula, vale o estado atual dela; a escritura
  mostra a área da data da venda (uma averbação posterior pode tê-la mudado), e a diferença
  vira observação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from arquiteto_auditor.config import Tolerancias, tolerancias
from arquiteto_auditor.dominio.catalogo import carregar_catalogo
from arquiteto_auditor.dominio.constatacao import Constatacao, Situacao
from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    ItemVerificacao,
    OrigemValor,
    StatusConfirmacao,
    StatusItem,
    ValorExtraido,
)
from arquiteto_auditor.dominio.numeros import formatar_numero
from arquiteto_auditor.dominio.parametros import ParametroAdotado
from arquiteto_auditor.verificacao.consistencia import (
    texto_comparavel,
    verificar_numeros,
    verificar_textos,
)
from arquiteto_auditor.verificacao.formulas import calcular_indice, formulas
from arquiteto_auditor.verificacao.regras import (
    REGRAS_DE_LIMITE,
    verificar_declarado,
    verificar_limite,
    verificar_soma,
)

FONTES_DA_AREA = ("matricula", "escritura", "prancha", "memorial")
GRAVIDADE = {StatusItem.NAO_ATENDE: 3, StatusItem.DIVERGENTE: 2, StatusItem.NAO_VERIFICAVEL: 1,
             StatusItem.ATENDE: 0}
# Chave do parâmetro → elemento da cota nas constatações de completude (COTA_INDEFINIDA).
ELEMENTO_DA_COTA = {"RECUO_FRONTAL": "recuo_frontal", "RECUO_LATERAL_E": "recuo_lateral_e",
                    "RECUO_LATERAL_D": "recuo_lateral_d", "RECUO_FUNDOS": "recuo_fundos",
                    "ALTURA_MAX": "altura_total", "MURO_ALTURA_MAX": "muro",
                    "LOTE_TESTADA_MIN": "testada"}
CAMPO_DO_PROJETO = {"RECUO_FRONTAL": "RECUO_FRONTAL", "RECUO_LATERAL_E": "RECUO_LATERAL_E",
                    "RECUO_LATERAL_D": "RECUO_LATERAL_D", "RECUO_FUNDOS": "RECUO_FUNDOS",
                    "ALTURA_MAX": "ALTURA", "MURO_ALTURA_MAX": "MURO_ALTURA",
                    "AREA_CONSTR_MIN": "AREA_CONSTR_TOTAL"}
INDICES = (("TO_MAX", "TO", "TO_DECLARADA", "taxa de ocupação", "%"),
           ("CA_MAX", "CA", "CA_DECLARADO", "coeficiente de aproveitamento", ""),
           ("PERMEAVEL_MIN", "PERMEAVEL", "PERMEAVEL_DECLARADA", "taxa de permeabilidade", "%"))
COMPLETUDE = ("NORTE_INDICADO", "ASSINATURA_AUTOR", "ASSINATURA_PROPRIETARIO",
              "ASSINATURA_DIGITAL_VALIDA")


@dataclass
class Fatos:
    """Tudo o que foi lido numa rodada de análise, por documento."""

    pranchas: dict[str, ValorExtraido] = field(default_factory=dict)
    memorial: dict[str, ValorExtraido] = field(default_factory=dict)
    matricula: dict[str, ValorExtraido] = field(default_factory=dict)  # estado atual + número
    escritura: dict[str, ValorExtraido] = field(default_factory=dict)
    parametros: dict[str, ParametroAdotado] = field(default_factory=dict)
    constatacoes: list[Constatacao] = field(default_factory=list)
    arquivos_pranchas: list[str] = field(default_factory=list)

    def por_fonte(self, campo: str) -> dict[str, ValorExtraido | None]:
        return {"prancha": self.pranchas.get(campo), "memorial": self.memorial.get(campo),
                "matricula": self.matricula.get(campo), "escritura": self.escritura.get(campo)}

    def area_do_terreno(self) -> ValorExtraido | None:
        for fonte in FONTES_DA_AREA:
            valor = self.por_fonte("TERRENO_AREA")[fonte]
            if valor is not None:
                return valor
        return None


def juntar(chave: str, itens: list[ItemVerificacao], escopo: str | None = None
           ) -> ItemVerificacao:
    """Um item a partir de vários (ex.: prancha e memorial): vale o status mais grave."""
    pior = max(itens, key=lambda i: GRAVIDADE[i.status])
    return ItemVerificacao(
        chave=chave, escopo=escopo, status=pior.status,
        mensagem=" ".join(i.mensagem for i in itens), valor_projeto=pior.valor_projeto,
        limite=pior.limite, margem=pior.margem, sugestao=pior.sugestao,
        evidencias=[e for i in itens for e in i.evidencias],
        observacoes=list(dict.fromkeys(o for i in itens for o in i.observacoes)),
        baixa_confianca=any(i.baixa_confianca for i in itens))


def _do_projeto(fatos: Fatos, campo: str) -> ValorExtraido | None:
    """Valor do projeto: o da prancha; na falta, o do memorial, pendente de confirmação."""
    if campo in fatos.pranchas:
        return fatos.pranchas[campo]
    reserva = fatos.memorial.get(campo)
    if reserva is None:
        return None
    nota = "Valor do memorial: não encontrado nas pranchas."
    return reserva.model_copy(update={
        "status": StatusConfirmacao.PENDENTE,
        "observacao": f"{reserva.observacao} {nota}" if reserva.observacao else nota})


def _derivado(valor: ValorExtraido | None, campo: str, texto: str | None) -> ValorExtraido | None:
    """Um pedaço de outro valor (ex.: o lote dentro do endereço do memorial)."""
    if valor is None or not texto:
        return None
    return valor.model_copy(update={"campo": campo, "valor": texto})


def _lote_e_quadra(valores: dict[str, ValorExtraido]) -> ValorExtraido | None:
    lote, quadra = valores.get("LOTE"), valores.get("QUADRA")
    if lote is not None or quadra is not None:
        base = lote or quadra
        texto = f"Lote {lote.valor if lote else '?'}, Quadra {quadra.valor if quadra else '?'}"
        return _derivado(base, "LOTE_QUADRA", texto)
    endereco = valores.get("ENDERECO")
    if endereco is None:
        return None
    normal = texto_comparavel(str(endereco.valor))
    achado_lote = re.search(r"\bLOTE (?:N )?(\w+)", normal)
    achado_quadra = re.search(r"\bQUADRA (?:N )?(\w+)", normal)
    if not (achado_lote or achado_quadra):
        return None
    texto = (f"Lote {achado_lote.group(1) if achado_lote else '?'}, "
             f"Quadra {achado_quadra.group(1) if achado_quadra else '?'}")
    return _derivado(endereco, "LOTE_QUADRA", texto)


# ------------------------------------------------------------------ identificação


def _revisao(fatos: Fatos) -> ItemVerificacao:
    revisao = fatos.pranchas.get("REVISAO")
    if revisao is None:
        return ItemVerificacao(chave="ID_REVISAO", status=StatusItem.NAO_VERIFICAVEL,
                               mensagem="Revisão do projeto não encontrada no carimbo.")
    diferentes = bool(revisao.observacao and "diferentes" in revisao.observacao)
    return ItemVerificacao(
        chave="ID_REVISAO", status=StatusItem.DIVERGENTE if diferentes else StatusItem.ATENDE,
        mensagem=(f"Revisão diferente entre as pranchas. {revisao.observacao}" if diferentes
                  else f"Mesma revisão em todas as pranchas: {revisao.valor}."),
        sugestao="Indicar a mesma revisão em todas as pranchas." if diferentes else None,
        evidencias=list(revisao.evidencias),
        baixa_confianca=revisao.status == StatusConfirmacao.PENDENTE and not diferentes)


def _proprietario(fatos: Fatos) -> ItemVerificacao:
    constatacao = next((c for c in fatos.constatacoes if c.chave == "ID_PROPRIETARIO"), None)
    if constatacao is not None and constatacao.situacao == Situacao.AUSENTE:
        return _ausente("ID_PROPRIETARIO", constatacao, fatos,
                        "Identificar o proprietário no carimbo das pranchas.")
    return verificar_textos("ID_PROPRIETARIO", "proprietário", {
        "prancha": fatos.pranchas.get("PROPRIETARIO"),
        "memorial": fatos.memorial.get("PROPRIETARIO"),
        "matricula": fatos.matricula.get("PROPRIETARIO")}, "nome")


def _identificacao(fatos: Fatos) -> list[ItemVerificacao]:
    p, m = fatos.pranchas, fatos.memorial
    condominio_memorial = m.get("CONDOMINIO") or m.get("ENDERECO")
    procurado = _onde_procurou(fatos)
    autor = juntar("ID_AUTOR_REGISTRO", [
        verificar_textos("ID_AUTOR_REGISTRO", "autor do projeto",
                         {"prancha": p.get("AUTOR"), "memorial": m.get("AUTOR")}, "nome",
                         ausente=StatusItem.NAO_ATENDE, onde_procurou=procurado),
        verificar_textos("ID_AUTOR_REGISTRO", "registro profissional (CAU/CREA)",
                         {"prancha": p.get("AUTOR_REGISTRO"),
                          "memorial": m.get("AUTOR_REGISTRO")}, "codigo",
                         ausente=StatusItem.NAO_ATENDE, onde_procurou=procurado)])
    return [
        verificar_textos("ID_MATRICULA", "número da matrícula", fatos.por_fonte("MATRICULA"),
                         "codigo"),
        verificar_textos("ID_CARTORIO", "cartório de registro", fatos.por_fonte("CARTORIO"),
                         "texto"),
        verificar_textos("ID_LOTE_QUADRA", "lote e quadra",
                         {"prancha": _lote_e_quadra(p), "memorial": _lote_e_quadra(m)},
                         "texto"),
        verificar_textos("ID_CONDOMINIO", "condomínio",
                         {"prancha": p.get("CONDOMINIO"), "memorial": condominio_memorial},
                         "texto"),
        verificar_textos("ID_ENDERECO", "endereço",
                         {"prancha": p.get("ENDERECO"), "memorial": m.get("ENDERECO")},
                         "texto"),
        autor,
        verificar_textos("ID_RRT_ART", "RRT/ART",
                         {"prancha": p.get("RRT"), "memorial": m.get("RRT")}, "codigo",
                         ausente=StatusItem.NAO_ATENDE, onde_procurou=procurado),
        _revisao(fatos),
        _proprietario(fatos),
    ]


# ------------------------------------------------------------------ consistência e aritmética


def _pavimentos(valores: dict[str, ValorExtraido]) -> dict[int, ValorExtraido]:
    achados = {}
    for campo, valor in valores.items():
        numero = re.fullmatch(r"AREA_CONSTR_PAV_(\d+)", campo)
        if numero:
            achados[int(numero.group(1))] = valor
    return dict(sorted(achados.items()))


def _consistencia(fatos: Fatos, tol: Tolerancias) -> list[ItemVerificacao]:
    areas = fatos.por_fonte("TERRENO_AREA")
    escritura = areas["escritura"]
    observacao_escritura = None
    if areas["matricula"] is not None and escritura is not None:
        areas["escritura"] = None
        if abs(float(escritura.valor) - float(areas["matricula"].valor)) > tol.area_m2:
            observacao_escritura = (
                f"A escritura indica {formatar_numero(float(escritura.valor))} m² (área na data "
                "da venda); vale o estado atual da matrícula, que inclui as averbações "
                "posteriores.")
    area = verificar_numeros("TERRENO_AREA", "área do terreno", areas, tol.area_m2)
    if observacao_escritura:
        area = area.model_copy(update={
            "observacoes": [*area.observacoes, observacao_escritura],
            "evidencias": [*area.evidencias, *escritura.evidencias]})
    itens = [
        area,
        verificar_numeros("TERRENO_TESTADA", "testada do terreno",
                          fatos.por_fonte("TERRENO_TESTADA"), tol.comprimento_m, " m"),
    ]
    pavimentos_p, pavimentos_m = _pavimentos(fatos.pranchas), _pavimentos(fatos.memorial)
    for numero in sorted(set(pavimentos_p) | set(pavimentos_m)):
        itens.append(verificar_numeros(
            "AREA_CONSTR_PAV", f"área construída do pavimento {numero}",
            {"prancha": pavimentos_p.get(numero), "memorial": pavimentos_m.get(numero)},
            tol.area_m2, escopo=f"pavimento={numero}"))
    itens.append(verificar_numeros(
        "AREA_CONSTR_TOTAL", "área construída total",
        {"prancha": fatos.pranchas.get("AREA_CONSTR_TOTAL"),
         "memorial": fatos.memorial.get("AREA_CONSTR_TOTAL")}, tol.area_m2))
    return itens


def _aritmetica(fatos: Fatos, tol: Tolerancias) -> list[ItemVerificacao]:
    quadro = fatos.pranchas if _pavimentos(fatos.pranchas) else fatos.memorial
    itens = [verificar_soma(list(_pavimentos(quadro).values()), quadro.get("AREA_CONSTR_TOTAL"),
                            tol.area_m2)]
    area_oficial = fatos.area_do_terreno()
    for _, codigo, chave, nome, unidade in INDICES:
        minima = tol.percentual if unidade == "%" else tol.coeficiente
        campo = formulas()[codigo].numerador
        conferidos = []
        documentos = [fatos.pranchas] if chave in fatos.pranchas else [fatos.memorial]
        for documento in documentos:
            declarado = documento.get(chave)
            if declarado is None:
                continue
            numerador = documento.get(campo) or _do_projeto(fatos, campo)
            area = documento.get("TERRENO_AREA") or area_oficial
            recalculado = calcular_indice(codigo, numerador, area, f"{codigo}_RECALCULADO")
            conferidos.append(verificar_declarado(chave, nome, declarado, recalculado, minima,
                                                  unidade))
        # Um documento sem dados para recalcular não esconde a conferência de outro.
        conclusivos = [i for i in conferidos if i.status != StatusItem.NAO_VERIFICAVEL]
        conferidos = conclusivos or conferidos
        itens.append(juntar(chave, conferidos) if conferidos else verificar_declarado(
            chave, nome, None, None, minima, unidade))
    return itens


# ------------------------------------------------------------------ parâmetros


def _constatacao_da_cota(fatos: Fatos, elemento: str | None) -> Constatacao | None:
    if elemento is None:
        return None
    escopo = f"elemento={elemento}"
    return next((c for c in fatos.constatacoes
                 if c.chave == "COTA_INDEFINIDA" and c.escopo == escopo), None)


def _contagem_de_pavimentos(fatos: Fatos) -> ValorExtraido | None:
    pavimentos = _pavimentos(fatos.pranchas)
    if not pavimentos:
        return None
    pendente = any(v.status == StatusConfirmacao.PENDENTE for v in pavimentos.values())
    return ValorExtraido(
        campo="PAVIMENTOS", valor=float(len(pavimentos)), origem=OrigemValor.CALCULADO,
        confianca=min(v.confianca for v in pavimentos.values()),
        calculado_de=[v.campo for v in pavimentos.values()],
        evidencias=[e for v in pavimentos.values() for e in v.evidencias],
        status=StatusConfirmacao.PENDENTE if pendente else StatusConfirmacao.AUTOMATICO,
        observacao="Pavimentos contados no quadro de áreas das pranchas.")


def _parametros(fatos: Fatos) -> list[ItemVerificacao]:
    area = fatos.area_do_terreno()
    itens = []
    for chave in REGRAS_DE_LIMITE:
        parametro = fatos.parametros.get(chave)
        if chave == "AREA_CONSTR_MIN" and parametro is None:
            continue  # só se aplica quando algum documento define o limite
        extra = {}
        sem_projeto = None
        if chave == "LOTE_AREA_MIN":
            projeto = area
        elif chave == "LOTE_TESTADA_MIN":
            projeto = _do_projeto(fatos, "TERRENO_TESTADA")
        elif chave == "PAVIMENTOS_MAX":
            projeto = _contagem_de_pavimentos(fatos)
        elif chave in CAMPO_DO_PROJETO:
            projeto = _do_projeto(fatos, CAMPO_DO_PROJETO[chave])
        else:  # índices
            _, codigo, *_ = next(i for i in INDICES if i[0] == chave)
            numerador = _do_projeto(fatos, formulas()[codigo].numerador)
            projeto = calcular_indice(codigo, numerador, area, f"{codigo}_PROJETO")
            extra = {"area_terreno": area, "numerador": numerador}
            if projeto is None:
                sem_projeto = (f"Não há dados para calcular: falta "
                               f"{'a área do terreno' if area is None else 'a área no quadro'}"
                               " de áreas.")
        constatacao = _constatacao_da_cota(fatos, ELEMENTO_DA_COTA.get(chave))
        if projeto is None and constatacao is not None and constatacao.situacao == Situacao.AUSENTE:
            sem_projeto = f"Cota não indicada nas pranchas ({constatacao.motivo})."
        itens.append(verificar_limite(chave, projeto, parametro, sem_projeto=sem_projeto,
                                      **extra))
    return itens


# ------------------------------------------------------------------ completude


def _onde_procurou(fatos: Fatos) -> list[Evidencia]:
    """Para uma ausência nas pranchas e no memorial: onde se procurou."""
    arquivos = list(fatos.arquivos_pranchas) or (["pranchas"] if fatos.pranchas else [])
    if fatos.memorial:
        arquivos.append(next(iter(fatos.memorial.values())).evidencias[0].documento)
    return [Evidencia(documento=a, pagina=1, trecho="[não encontrado neste documento]")
            for a in arquivos]


def _evidencias_descritas(fatos: Fatos, descricao: str) -> list[Evidencia]:
    """Sem texto a citar (ex.: uma ausência): a evidência diz onde se procurou e o que se viu."""
    arquivos = fatos.arquivos_pranchas or ["pranchas"]
    return [Evidencia(documento=a, pagina=1, trecho=f"[{descricao}]") for a in arquivos]


def _ausente(chave: str, constatacao: Constatacao, fatos: Fatos, sugestao: str,
             escopo: str | None = None) -> ItemVerificacao:
    evidencias = list(constatacao.evidencias) or _evidencias_descritas(
        fatos, f"não encontrado: {constatacao.motivo}")
    alterada = constatacao.situacao == Situacao.ALTERADA
    return ItemVerificacao(
        chave=chave, escopo=escopo, status=StatusItem.NAO_ATENDE,
        mensagem=(f"Documento alterado depois de assinado: {constatacao.motivo}." if alterada
                  else f"Não encontrado: {constatacao.motivo}."),
        sugestao=sugestao, evidencias=evidencias)


SUGESTOES = {
    "COTA_INDEFINIDA": "Indicar a cota numérica dessa dimensão nas pranchas.",
    "NORTE_INDICADO": "Indicar o Norte nas plantas de situação e de localização.",
    "ASSINATURA_AUTOR": "Assinar digitalmente todas as pranchas (autor do projeto).",
    "ASSINATURA_PROPRIETARIO": "Colher a assinatura do proprietário em todas as pranchas.",
    "ASSINATURA_DIGITAL_VALIDA": "Gerar de novo o PDF e assinar a versão final, sem alterá-la "
                                 "depois. Conferir também no validador do ITI.",
}


def _completude(fatos: Fatos) -> list[ItemVerificacao]:
    itens = []
    for c in fatos.constatacoes:
        if c.chave == "COTA_INDEFINIDA" and c.situacao != Situacao.PRESENTE:
            itens.append(_ausente(c.chave, c, fatos, SUGESTOES[c.chave], c.escopo))
    for chave in COMPLETUDE:
        constatacao = next((c for c in fatos.constatacoes if c.chave == chave), None)
        if constatacao is None:
            itens.append(ItemVerificacao(
                chave=chave, status=StatusItem.NAO_VERIFICAVEL,
                mensagem="Não foi possível verificar (nenhuma assinatura digital ou autor "
                         "não identificado)." if chave.startswith("ASSINATURA")
                else "Não foi possível verificar."))
        elif constatacao.situacao == Situacao.PRESENTE:
            itens.append(ItemVerificacao(
                chave=chave, status=StatusItem.ATENDE,
                mensagem=constatacao.motivo.capitalize() + "." if constatacao.motivo
                else "Presente.",
                evidencias=list(constatacao.evidencias)
                or _evidencias_descritas(fatos, constatacao.motivo or "presente")))
        else:
            itens.append(_ausente(chave, constatacao, fatos, SUGESTOES[chave]))
    return itens


# ------------------------------------------------------------------ motor


def verificar(fatos: Fatos, tol: Tolerancias | None = None) -> list[ItemVerificacao]:
    """Todos os itens do catálogo, na ordem do catálogo."""
    tol = tol or tolerancias()
    itens = (_identificacao(fatos) + _consistencia(fatos, tol) + _aritmetica(fatos, tol)
             + _parametros(fatos) + _completude(fatos))
    ordem = {chave: i for i, chave in enumerate(carregar_catalogo())}
    return sorted(itens, key=lambda item: ordem.get(item.chave, len(ordem)))
