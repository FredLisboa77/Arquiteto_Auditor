"""Regras do motor de verificação: projeto × parâmetro e declarado × recalculado.

Tudo aqui é código determinístico (CLAUDE.md §3): o LLM não calcula, não compara e não
decide "atende/não atende". Cada regra devolve um ItemVerificacao com:
- status: atende / não atende / divergente / não foi possível verificar (com o motivo);
- margem: folga (positiva) ou falta (negativa), na unidade do parâmetro;
- sugestão com a quantidade (ex.: "reduzir ≈ 8,00 m² de projeção");
- evidências do projeto e do parâmetro, e as observações (fórmula, conflito com o condomínio);
- baixa_confianca quando algum valor usado está pendente de confirmação.
Valor exatamente no limite ATENDE (o limite é permitido: "máximo 60%" aceita 60%).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from arquiteto_auditor.dominio.modelos import (
    ItemVerificacao,
    StatusConfirmacao,
    StatusItem,
    ValorExtraido,
)
from arquiteto_auditor.dominio.numeros import casas_decimais, formatar_numero
from arquiteto_auditor.dominio.parametros import ParametroAdotado

FOLGA_NUMERICA = 1e-6  # só para erros de arredondamento do computador, não é tolerância


def maiuscula(texto: str) -> str:
    """Primeira letra maiúscula, o resto como está ("RRT/ART" continua "RRT/ART")."""
    return texto[:1].upper() + texto[1:]


@dataclass(frozen=True)
class RegraLimite:
    nome: str  # como aparece na mensagem: "taxa de ocupação"
    limite: Literal["minimo", "maximo"]
    unidade: str  # "%", "m", "m²", "" ou " pavimento(s)"
    casas: int = 2


REGRAS_DE_LIMITE: dict[str, RegraLimite] = {
    "LOTE_AREA_MIN": RegraLimite("área do lote", "minimo", " m²"),
    "LOTE_TESTADA_MIN": RegraLimite("testada do lote", "minimo", " m"),
    "RECUO_FRONTAL": RegraLimite("recuo frontal", "minimo", " m"),
    "RECUO_LATERAL_E": RegraLimite("recuo lateral esquerdo", "minimo", " m"),
    "RECUO_LATERAL_D": RegraLimite("recuo lateral direito", "minimo", " m"),
    "RECUO_FUNDOS": RegraLimite("recuo de fundos", "minimo", " m"),
    "TO_MAX": RegraLimite("taxa de ocupação", "maximo", "%"),
    "CA_MAX": RegraLimite("coeficiente de aproveitamento", "maximo", ""),
    "PERMEAVEL_MIN": RegraLimite("taxa de permeabilidade", "minimo", "%"),
    "ALTURA_MAX": RegraLimite("altura da edificação", "maximo", " m"),
    "PAVIMENTOS_MAX": RegraLimite("número de pavimentos", "maximo", " pavimento(s)", casas=0),
    "MURO_ALTURA_MAX": RegraLimite("altura do muro", "maximo", " m"),
    "AREA_CONSTR_MIN": RegraLimite("área construída total", "minimo", " m²"),
}


def _f(valor: float, regra: RegraLimite) -> str:
    return f"{formatar_numero(valor, regra.casas)}{regra.unidade}"


def _pendente(*valores: ValorExtraido | None) -> bool:
    return any(v is not None and v.status == StatusConfirmacao.PENDENTE for v in valores)


def _sugestao(chave: str, valor: float, limite: float, area_terreno: float | None,
              numerador: float | None) -> str:
    """O que fazer para atender, com a quantidade (só para itens que não atendem)."""
    diferenca = abs(valor - limite)
    m = formatar_numero
    if chave in ("TO_MAX", "CA_MAX") and area_terreno and numerador is not None:
        fator = 100 if chave == "TO_MAX" else 1
        maximo = limite * area_terreno / fator
        oque = "de projeção" if chave == "TO_MAX" else "de área construída computável"
        return (f"Em terreno de {m(area_terreno)} m², reduzir ≈ {m(numerador - maximo)} m² "
                f"{oque} (de {m(numerador)} para no máximo {m(maximo)} m²).")
    if chave == "PERMEAVEL_MIN" and area_terreno and numerador is not None:
        minimo = limite * area_terreno / 100
        return (f"Em terreno de {m(area_terreno)} m², aumentar ≈ {m(minimo - numerador)} m² "
                f"de área permeável (de {m(numerador)} para no mínimo {m(minimo)} m²).")
    if chave.startswith("RECUO_"):
        return f"Aumentar o recuo em {m(diferenca)} m (mínimo de {m(limite)} m)."
    if chave == "ALTURA_MAX":
        return f"Reduzir a altura da edificação em {m(diferenca)} m (máximo de {m(limite)} m)."
    if chave == "MURO_ALTURA_MAX":
        return f"Reduzir a altura do muro em {m(diferenca)} m (máximo de {m(limite)} m)."
    if chave == "PAVIMENTOS_MAX":
        return f"Reduzir {m(diferenca, 0)} pavimento(s) (máximo de {m(limite, 0)})."
    if chave == "AREA_CONSTR_MIN":
        return f"Aumentar a área construída em {m(diferenca)} m² (mínimo de {m(limite)} m²)."
    if chave in ("LOTE_AREA_MIN", "LOTE_TESTADA_MIN"):
        return ("O lote está abaixo do mínimo da zona: confirme na prefeitura se ele é regular "
                "(ex.: aprovado antes da lei atual).")
    return "Ajustar o projeto ao limite."


def verificar_limite(chave: str, projeto: ValorExtraido | None,
                     parametro: ParametroAdotado | None, *,
                     area_terreno: ValorExtraido | None = None,
                     numerador: ValorExtraido | None = None,
                     sem_projeto: str | None = None) -> ItemVerificacao:
    """Projeto × parâmetro (mínimo ou máximo), com margem e sugestão.

    area_terreno e numerador (projeção, área construída ou permeável) servem para a
    sugestão em m² nos índices. sem_projeto: motivo, quando o valor do projeto falta.
    """
    regra = REGRAS_DE_LIMITE[chave]
    evidencias = list(projeto.evidencias) if projeto else []
    if parametro is None:
        return ItemVerificacao(
            chave=chave, status=StatusItem.NAO_VERIFICAVEL, evidencias=evidencias,
            valor_projeto=float(projeto.valor) if projeto else None,
            mensagem=(f"Limite de {regra.nome} não encontrado na lei municipal nem na norma do "
                      "condomínio: informe o parâmetro para verificar."))
    evidencias += parametro.valor.evidencias
    limite = float(parametro.valor.valor)
    observacoes = [o for o in (parametro.observacao, parametro.valor.observacao) if o]
    if projeto is None:
        return ItemVerificacao(
            chave=chave, status=StatusItem.NAO_VERIFICAVEL, evidencias=evidencias,
            limite=limite, observacoes=observacoes,
            mensagem=sem_projeto or f"Valor de {regra.nome} do projeto não encontrado.")
    if projeto.observacao:  # fórmula usada, valor vindo do memorial...
        observacoes.insert(0, projeto.observacao)

    valor = float(projeto.valor)
    margem = limite - valor if regra.limite == "maximo" else valor - limite
    atende = margem >= -FOLGA_NUMERICA
    palavra = "máx." if regra.limite == "maximo" else "mín."
    if atende:
        situacao = "no limite" if abs(margem) <= FOLGA_NUMERICA else f"folga de {_f(margem, regra)}"
    else:
        verbo = "excede" if regra.limite == "maximo" else "faltam"
        situacao = f"{verbo} {_f(-margem, regra)}"
    if regra.unidade == "%":
        situacao = situacao.replace("%", " p.p.")  # diferença de porcentagens: pontos percentuais
    fonte = "prefeitura" if parametro.fonte == "prefeitura" else "condomínio"
    mensagem = (f"{maiuscula(regra.nome)} do projeto: {_f(valor, regra)} · {palavra} "
                f"{_f(limite, regra)} ({fonte}) · {situacao}")
    mensagem += "" if mensagem.endswith(".") else "."
    return ItemVerificacao(
        chave=chave, status=StatusItem.ATENDE if atende else StatusItem.NAO_ATENDE,
        mensagem=mensagem, valor_projeto=valor, limite=limite, margem=round(margem, 6),
        sugestao=None if atende else _sugestao(
            chave, valor, limite,
            float(area_terreno.valor) if area_terreno else None,
            float(numerador.valor) if numerador else None),
        evidencias=evidencias, observacoes=observacoes,
        baixa_confianca=_pendente(projeto, parametro.valor))


# ------------------------------------------------------------------ declarado × recalculado


def tolerancia_do_declarado(declarado: ValorExtraido, minima: float) -> float:
    """Meia unidade da última casa decimal escrita ("35,23" → 0,005), nunca menos que a mínima."""
    casas = None
    for evidencia in declarado.evidencias:
        casas = casas_decimais(evidencia.trecho, float(declarado.valor))
        if casas is not None:
            break
    meia_unidade = 0.5 * 10 ** -(2 if casas is None else casas)
    return max(minima, meia_unidade)


def verificar_declarado(chave: str, nome: str, declarado: ValorExtraido | None,
                        recalculado: ValorExtraido | None, tolerancia_minima: float,
                        unidade: str = "") -> ItemVerificacao:
    """Índice declarado no projeto × recalculado pelo código (atende ou divergente)."""
    if declarado is None or recalculado is None:
        falta = "declarado(a) no projeto" if declarado is None else "para recalcular"
        return ItemVerificacao(
            chave=chave, status=StatusItem.NAO_VERIFICAVEL,
            evidencias=list(declarado.evidencias) if declarado else [],
            mensagem=f"Não há dados suficientes: {nome} não {falta}.")
    valor, calculo = float(declarado.valor), float(recalculado.valor)
    tolerancia = tolerancia_do_declarado(declarado, tolerancia_minima)
    diferenca = valor - calculo
    confere = abs(diferenca) <= tolerancia + FOLGA_NUMERICA
    texto = (f"{maiuscula(nome)} declarado(a): {formatar_numero(valor)}{unidade} · "
             f"recalculado(a): {formatar_numero(calculo, 4)}{unidade}")
    return ItemVerificacao(
        chave=chave, status=StatusItem.ATENDE if confere else StatusItem.DIVERGENTE,
        mensagem=texto + (" · confere." if confere else
                          f" · diferença de {formatar_numero(diferenca, 4)}{unidade}."),
        valor_projeto=valor, limite=round(calculo, 6), margem=round(diferenca, 6),
        sugestao=None if confere else (
            f"Corrigir o valor declarado para {formatar_numero(calculo)}{unidade} ou rever as "
            "áreas usadas no cálculo."),
        evidencias=[*declarado.evidencias, *recalculado.evidencias],
        observacoes=[recalculado.observacao] if recalculado.observacao else [],
        baixa_confianca=_pendente(declarado, recalculado))


def verificar_soma(parciais: list[ValorExtraido], total: ValorExtraido | None,
                   tolerancia: float, chave: str = "AREA_CONSTR_SOMA") -> ItemVerificacao:
    """Soma das áreas dos pavimentos × área total declarada (atende ou divergente)."""
    if not parciais or total is None:
        return ItemVerificacao(
            chave=chave, status=StatusItem.NAO_VERIFICAVEL,
            mensagem="Não há áreas dos pavimentos e área total declaradas para somar.")
    soma = sum(float(p.valor) for p in parciais)
    diferenca = float(total.valor) - soma
    confere = abs(diferenca) <= tolerancia + FOLGA_NUMERICA
    parcelas = " + ".join(formatar_numero(float(p.valor)) for p in parciais)
    return ItemVerificacao(
        chave=chave, status=StatusItem.ATENDE if confere else StatusItem.DIVERGENTE,
        mensagem=(f"Soma dos pavimentos: {parcelas} = {formatar_numero(soma)} m² · total "
                  f"declarado: {formatar_numero(float(total.valor))} m²"
                  + (" · confere." if confere else
                     f" · diferença de {formatar_numero(diferenca)} m².")),
        valor_projeto=float(total.valor), limite=round(soma, 6), margem=round(diferenca, 6),
        sugestao=None if confere else "Corrigir a área total ou as áreas dos pavimentos.",
        evidencias=[e for v in (*parciais, total) for e in v.evidencias],
        baixa_confianca=_pendente(total, *parciais))
