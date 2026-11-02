"""Leitura do memorial descritivo (Fase 7): os mesmos campos das pranchas, em texto.

Memoriais vêm de vários jeitos (docs/06 §6.2): campos "Rótulo: valor" (identificação,
afastamentos), quadro de áreas em tabela (às vezes colado como IMAGEM — lido pelo OCR na
ingestão) e frases ("o terreno possui área de 400,00 m²"). Por isso juntam-se três leituras
já existentes — rótulos (como no carimbo), quadro de áreas e frases — mais o bloco de
assinatura do responsável técnico (o nome e, logo abaixo, "Arquiteto(a) e Urbanista - CAU
A123"). Os achados do mesmo campo são consolidados: se discordam, o valor fica pendente.
"""

from __future__ import annotations

import re
from collections import defaultdict

from arquiteto_auditor.dominio.documento import DocumentoLido, OrigemPalavra, PaginaLida
from arquiteto_auditor.dominio.modelos import Evidencia, OrigemValor, ValorExtraido
from arquiteto_auditor.extracao.consolidar import consolidar
from arquiteto_auditor.extracao.frases import ler_frases
from arquiteto_auditor.extracao.pranchas.carimbo import ler_carimbo
from arquiteto_auditor.extracao.pranchas.linhas import LinhaTexto, agrupar_linhas
from arquiteto_auditor.extracao.pranchas.quadro import ler_quadro_areas
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido

_REGISTRO = re.compile(r"\b(?:CAU|CREA)\b[\s:-]*[A-Z]{0,2}\s?\d[\d.\-/]*", re.IGNORECASE)
_NOME = re.compile(r"^[A-Za-zÀ-ú'][A-Za-zÀ-ú'.\- ]+$")  # só letras: não é rótulo nem frase
CONFIANCA_ASSINATURA = 0.8


def _valor(campo: str, texto: str, linha: LinhaTexto, pagina: PaginaLida,
           arquivo: str) -> ValorExtraido:
    ocr = any(p.origem == OrigemPalavra.OCR for p in linha.palavras)
    return ValorExtraido(
        campo=campo, valor=texto, origem=OrigemValor.OCR if ocr else OrigemValor.VETORIAL,
        confianca=round(CONFIANCA_ASSINATURA * (linha.confianca if ocr else 1.0), 3),
        evidencias=[Evidencia(documento=arquivo, pagina=pagina.numero, trecho=linha.texto,
                              bbox=linha.bbox, confianca_ocr=linha.confianca if ocr else None)])


def _assinatura_tecnica(pagina: PaginaLida, arquivo: str) -> list[ValorExtraido]:
    """Registro (CAU/CREA) sem rótulo e o nome na linha logo acima, se parecer um nome."""
    linhas = [ln for ln in agrupar_linhas(pagina.palavras) if not ln.vertical]
    valores = []
    for i, linha in enumerate(linhas):
        if ":" in linha.texto or not (registro := _REGISTRO.search(linha.texto)):
            continue  # com rótulo, o leitor de rótulos já leu
        valores.append(_valor("AUTOR_REGISTRO", registro.group().strip(), linha, pagina,
                              arquivo))
        acima = linhas[i - 1] if i > 0 else None
        if (acima is not None and _NOME.match(acima.texto) and len(acima.texto.split()) >= 2
                and linha.bbox[1] - acima.bbox[3] <= 2 * linha.altura):
            valores.append(_valor("AUTOR", acima.texto, acima, pagina, arquivo))
    return valores


def ler_memorial(documento: DocumentoLido) -> dict[str, ValorExtraido]:
    achados: dict[str, list[ValorExtraido]] = defaultdict(list)
    for pagina in documento.paginas:
        for leitor in (ler_carimbo, ler_quadro_areas, _assinatura_tecnica):
            for valor in leitor(pagina, documento.arquivo):
                achados[valor.campo].append(valor)
    for valor in ler_frases(TextoCorrido(documento), documento.arquivo):
        achados[valor.campo].append(valor)
    return {campo: consolidar(lista) for campo, lista in achados.items()}
