"""Consistência entre documentos: o MESMO dado precisa ser igual onde aparece.

Ex.: a área do terreno na prancha, no memorial, na matrícula (estado atual) e na escritura.
- números: iguais dentro da tolerância (arredondamento) → atende; senão → divergente;
- códigos (matrícula, RRT): só os dígitos contam ("81.753" = "81753");
- nomes e endereços: maiúsculas/acentos/pontuação não contam, e um pode conter o outro
  (o carimbo corta textos longos; o memorial escreve o endereço completo);
- o dado em um documento só: não há com o que comparar → "não foi possível verificar";
- diferença em que algum valor está pendente (ex.: OCR com baixa confiança) → "não foi
  possível verificar", pedindo confirmação: a diferença pode ser só erro de leitura.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    ItemVerificacao,
    StatusConfirmacao,
    StatusItem,
    ValorExtraido,
)
from arquiteto_auditor.dominio.numeros import formatar_numero
from arquiteto_auditor.verificacao.regras import maiuscula

FOLGA_NUMERICA = 1e-6
NOMES_DAS_FONTES = {"prancha": "pranchas", "memorial": "memorial", "matricula": "matrícula",
                    "escritura": "escritura"}


def texto_comparavel(texto: str) -> str:
    """Maiúsculas, sem acentos e sem pontuação, com um espaço entre as palavras."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", str(texto))
                         if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w]+", " ", sem_acento.upper()).split())


def mesmo_codigo(a: str, b: str) -> bool:
    da, db = re.sub(r"\D", "", str(a)), re.sub(r"\D", "", str(b))
    if da or db:
        return da == db
    return texto_comparavel(a) == texto_comparavel(b)


def mesmo_texto(a: str, b: str) -> bool:
    """Um contém o outro (ex.: "Alameda das Hortênsias, 309" no endereço completo)."""
    ta, tb = texto_comparavel(a), texto_comparavel(b)
    if not ta or not tb:
        return False
    return ta in tb or tb in ta


def mesmo_nome(a: str, b: str) -> bool:
    """As palavras de um nome estão todas no outro (nome completo × abreviado)."""
    pa, pb = set(texto_comparavel(a).split()), set(texto_comparavel(b).split())
    return bool(pa and pb) and (pa <= pb or pb <= pa)


def _lista(valores: dict[str, ValorExtraido], formatar) -> str:
    return " · ".join(f"{NOMES_DAS_FONTES.get(f, f)}: {formatar(v)}" for f, v in valores.items())


def _resultado(chave: str, nome: str, valores: dict[str, ValorExtraido], iguais: bool,
               formatar, escopo: str | None, ausente: StatusItem,
               onde_procurou: list[Evidencia] | None) -> ItemVerificacao:
    evidencias = [e for v in valores.values() for e in v.evidencias]
    pendente = any(v.status == StatusConfirmacao.PENDENTE for v in valores.values())
    observacoes = [v.observacao for v in valores.values() if v.observacao]
    if not valores:
        # "Não atende" por ausência precisa de evidência: onde se procurou. Sem ela (nenhum
        # documento enviado), não dá para afirmar a ausência.
        status = ausente if onde_procurou else StatusItem.NAO_VERIFICAVEL
        return ItemVerificacao(chave=chave, escopo=escopo, status=status,
                               evidencias=list(onde_procurou or []),
                               mensagem=f"{maiuscula(nome)} não encontrado(a) nos documentos.")
    if len(valores) == 1:
        [(fonte, valor)] = valores.items()
        return ItemVerificacao(
            chave=chave, escopo=escopo, status=StatusItem.NAO_VERIFICAVEL,
            evidencias=evidencias, observacoes=observacoes, baixa_confianca=pendente,
            mensagem=(f"{maiuscula(nome)} só encontrado(a) em: "
                      f"{NOMES_DAS_FONTES.get(fonte, fonte)} ({formatar(valor)}); não há com o "
                      "que comparar."))
    lista = _lista(valores, formatar)
    if not iguais and pendente:
        return ItemVerificacao(
            chave=chave, escopo=escopo, status=StatusItem.NAO_VERIFICAVEL,
            mensagem=(f"{maiuscula(nome)} parece diferente entre os documentos — {lista} —, mas "
                      "há leitura incerta: confirme os valores."),
            evidencias=evidencias, observacoes=observacoes, baixa_confianca=True)
    return ItemVerificacao(
        chave=chave, escopo=escopo,
        status=StatusItem.ATENDE if iguais else StatusItem.DIVERGENTE,
        mensagem=(f"{maiuscula(nome)} igual nos documentos — {lista}." if iguais else
                  f"{maiuscula(nome)} diferente entre os documentos — {lista}."),
        sugestao=None if iguais else f"Corrigir {nome} nos documentos para o valor correto.",
        evidencias=evidencias, observacoes=observacoes, baixa_confianca=pendente)


def verificar_numeros(chave: str, nome: str, valores: dict[str, ValorExtraido | None],
                      tolerancia: float, unidade: str = " m²", escopo: str | None = None,
                      ausente: StatusItem = StatusItem.NAO_VERIFICAVEL,
                      onde_procurou: list[Evidencia] | None = None) -> ItemVerificacao:
    presentes = {f: v for f, v in valores.items() if v is not None}
    numeros = [float(v.valor) for v in presentes.values()]
    iguais = not numeros or max(numeros) - min(numeros) <= tolerancia + FOLGA_NUMERICA
    return _resultado(chave, nome, presentes, iguais,
                      lambda v: f"{formatar_numero(float(v.valor))}{unidade}", escopo, ausente,
                      onde_procurou)


def verificar_textos(chave: str, nome: str, valores: dict[str, ValorExtraido | None],
                     modo: Literal["codigo", "texto", "nome"], escopo: str | None = None,
                     ausente: StatusItem = StatusItem.NAO_VERIFICAVEL,
                     onde_procurou: list[Evidencia] | None = None) -> ItemVerificacao:
    presentes = {f: v for f, v in valores.items() if v is not None and str(v.valor).strip()}
    comparar = {"codigo": mesmo_codigo, "texto": mesmo_texto, "nome": mesmo_nome}[modo]
    lista = [str(v.valor) for v in presentes.values()]
    iguais = all(comparar(lista[0], outro) for outro in lista[1:])
    return _resultado(chave, nome, presentes, iguais, lambda v: str(v.valor), escopo, ausente,
                      onde_procurou)
