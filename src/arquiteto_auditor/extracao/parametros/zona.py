"""Zona do lote na lei de uso do solo: nunca presumida (docs/04, critério da Fase 8).

As leis descrevem o perímetro de cada zona citando os loteamentos e condomínios que ela
abrange ("ZR-2 - Zona Residencial 2: compreende as áreas dos seguintes loteamentos e
condomínios: ..., Residencial Correia, ..."). A zona do lote é a do parágrafo que cita o
nome do condomínio: o último código de zona escrito antes do nome, no mesmo trecho.

- o nome aparece com uma zona só → zona identificada;
- aparece com zonas diferentes → pendente, com as outras zonas na observação;
- não aparece (ou sem código de zona antes) → None: a interface pergunta ao revisor.
"""

from __future__ import annotations

import re

from arquiteto_auditor.dominio.modelos import OrigemValor, ValorExtraido
from arquiteto_auditor.extracao.consolidar import consolidar
from arquiteto_auditor.extracao.parametros.trechos import Trecho
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido, normalizar

CAMPO = "ZONA"
CONFIANCA = 0.9

# Código de zona em maiúsculas: ZR-2, ZR2, ZM, ZEIS, ZPA... ("Zona" e "ZONA" não contam).
_CODIGO = re.compile(r"\b(Z[A-Z]{0,4}(?:-?\d{1,2})?)\b")
_NAO_CODIGOS = {"ZONA", "ZONAS"}
_PREFIXOS_GENERICOS = ("CONDOMINIO ", "CONDOMINIO RESIDENCIAL ")


def _variantes_do_nome(nome: str) -> list[str]:
    """O nome como está e sem o prefixo "Condomínio" (a lei pode omiti-lo)."""
    normal = " ".join(normalizar(nome).split())
    variantes = [normal]
    for prefixo in _PREFIXOS_GENERICOS:
        if normal.startswith(prefixo) and len(normal) > len(prefixo) + 3:
            variantes.append(normal[len(prefixo):])
    return variantes


def _padrao(nome: str) -> re.Pattern:
    return re.compile(r"\b" + r"\s+".join(re.escape(p) for p in nome.split()) + r"\b")


def ultimo_codigo(texto: str) -> re.Match | None:
    codigos = [m for m in _CODIGO.finditer(texto) if m.group(1) not in _NAO_CODIGOS]
    return codigos[-1] if codigos else None


def identificar_zona(trechos: list[Trecho], corrido: TextoCorrido, nome_condominio: str | None,
                     arquivo: str) -> ValorExtraido | None:
    """Zona do lote pelo nome do condomínio no texto da lei (ver o início do módulo)."""
    if not nome_condominio or not nome_condominio.strip():
        return None
    for variante in _variantes_do_nome(nome_condominio):
        achados = _mencoes(trechos, corrido, _padrao(variante), arquivo)
        if achados:
            return consolidar(achados)
    return None


def _mencoes(trechos: list[Trecho], corrido: TextoCorrido, padrao: re.Pattern,
             arquivo: str) -> list[ValorExtraido]:
    achados = []
    for trecho in trechos:
        original = corrido.texto[trecho.inicio:trecho.fim]
        normal = normalizar(original)  # mesmo tamanho: as posições valem nos dois
        for mencao in padrao.finditer(normal):
            codigo = ultimo_codigo(original[:mencao.start()])
            if codigo is None:
                continue
            evidencia = corrido.evidencia(trecho.inicio + codigo.start(),
                                          trecho.inicio + mencao.end(), arquivo)
            ocr = evidencia.confianca_ocr is not None
            achados.append(ValorExtraido(
                campo=CAMPO, valor=codigo.group(1),
                origem=OrigemValor.OCR if ocr else OrigemValor.VETORIAL,
                confianca=CONFIANCA, evidencias=[evidencia]))
    return achados

