"""Leitura da escritura pública de compra e venda (Fase 7).

Linguagem padrão dos tabelionatos (igual em todo o país):
- "LIVRO 308 - FOLHAS 73/76" no cabeçalho;
- "SAIBAM quantos esta pública escritura virem que, AOS 02 de maio de 2015, ..." (lavratura);
- "OUTORGANTE VENDEDOR(A): ..." e "OUTORGADO(A) COMPRADOR(A): ...";
- "com a área de 395,00 m² (trezentos e noventa e cinco metros quadrados)";
- "Imóvel matriculado sob nº 71.677".
Campo não encontrado fica fora do resultado e vira pendência. Valor com OCR de baixa
confiança, ou área que não confere com o extenso, fica pendente de confirmação.
"""

from __future__ import annotations

import re

from arquiteto_auditor.config import limiar_confianca_ocr
from arquiteto_auditor.dominio.datas import encontrar_data
from arquiteto_auditor.dominio.documento import DocumentoLido
from arquiteto_auditor.dominio.modelos import OrigemValor, StatusConfirmacao, ValorExtraido
from arquiteto_auditor.dominio.registro import EscrituraLida
from arquiteto_auditor.extracao.registro.comum import ler_area, ler_nome
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido, normalizar

CONFIANCA = 0.9

_NUMERO = r"(?:N[º°O.]?)?\s*"  # "nº" opcional (o "º" conta como letra nas expressões)
_LIVRO_FOLHAS = re.compile(rf"LIVRO\s*{_NUMERO}(?P<livro>\d+)\W{{1,4}}FOLHAS?\s*{_NUMERO}"
                           r"(?P<folhas>\d+(?:\s*[/-]\s*\d+)?)")
_LAVRATURA = re.compile(r"\bAOS\s+")
# Rótulos das partes, tolerantes à sujeira de OCR ("COMPRADOR(AY).:", "OUTORGADO(A) : ..."),
# mas sempre com os dois-pontos no fim: a linha de assinaturas do fecho não é rótulo.
_PARENTESES = r"(?:\s*\([^)]{1,4}\))?"
_VENDEDOR = re.compile(rf"OUTORGANTES?{_PARENTESES}[\s:.]{{1,4}}VENDEDOR\w*{_PARENTESES}"
                       r"[^\w:\n]{0,3}:\s*|TRANSMITENTES?\s*:\s*")
_COMPRADOR = re.compile(rf"OUTORGAD[OA]S?{_PARENTESES}[\s:.]{{1,4}}COMPRADOR\w*{_PARENTESES}"
                        r"[^\w:\n]{0,3}:\s*|ADQUIRENTES?\s*:\s*")
_MATRICULA = re.compile(rf"MATRICULAD[OA]\s+SOB\s+(?:O\s+)?{_NUMERO}(?P<numero>\d[\d.]*\d)"
                        rf"|MATRICULA\s+{_NUMERO}(?P<numero2>\d[\d.]*\d)")


def ler_escritura(documento: DocumentoLido) -> EscrituraLida:
    corrido = TextoCorrido(documento)
    plano = corrido.texto.replace("\n", " ")
    normalizado = normalizar(plano)
    pendencias: list[str] = []
    campos: dict[str, ValorExtraido] = {}

    def guardar(campo, valor, trecho, confianca_de, unidade=None, motivo_extra=None):
        evidencia = corrido.evidencia(*trecho, documento.arquivo)
        ocr = corrido.confianca(*confianca_de)
        evidencia = evidencia.model_copy(update={"confianca_ocr": ocr})
        motivos = [motivo_extra] if motivo_extra else []
        if ocr is not None and ocr < limiar_confianca_ocr():
            motivos.append(f"leitura (OCR) com baixa confiança ({ocr:.2f})")
        campos[campo] = ValorExtraido(
            campo=campo, valor=valor, unidade=unidade,
            origem=OrigemValor.OCR if corrido.confianca(*trecho) is not None
            else OrigemValor.VETORIAL,
            confianca=round(CONFIANCA * (ocr if ocr is not None else 1.0), 3),
            evidencias=[evidencia],
            status=StatusConfirmacao.PENDENTE if motivos else StatusConfirmacao.AUTOMATICO,
            observacao=("Confirme: " + "; ".join(motivos) + ".") if motivos else None)

    if m := _LIVRO_FOLHAS.search(normalizado):
        guardar("LIVRO", m["livro"], (m.start(), m.end()), m.span("livro"))
        guardar("FOLHAS", re.sub(r"\s", "", m["folhas"]), (m.start(), m.end()),
                m.span("folhas"))
    if m := _LAVRATURA.search(normalizado):
        achado = encontrar_data(plano[m.end():m.end() + 40])
        if achado:
            data, a, b = achado
            guardar("DATA_LAVRATURA", data.strftime("%d/%m/%Y"), (m.start(), m.end() + b),
                    (m.end() + a, m.end() + b))
    for campo, padrao in (("VENDEDOR", _VENDEDOR), ("COMPRADOR", _COMPRADOR)):
        m = padrao.search(normalizado)
        nome = ler_nome(plano, m.end()) if m else None
        if nome:
            guardar(campo, nome.texto, (m.start(), nome.fim), (m.end(), nome.fim),
                    motivo_extra="sinais soltos do OCR removidos do nome" if nome.limpo
                    else None)
    if area := ler_area(plano, normalizado, 0, len(plano)):
        divergente = (f"o número não confere com o extenso ({area.extenso} m²)"
                      if area.extenso is not None and area.extenso != int(area.valor) else None)
        guardar("TERRENO_AREA", area.valor, (area.inicio, area.fim),
                (area.inicio_numero, area.fim_numero), "m2", divergente)
    if m := _MATRICULA.search(normalizado):
        grupo = "numero" if m["numero"] else "numero2"
        guardar("MATRICULA", m[grupo], (m.start(), m.end()), m.span(grupo))

    for campo in ("COMPRADOR", "TERRENO_AREA", "DATA_LAVRATURA"):
        if campo not in campos:
            pendencias.append(f"Escritura: {campo.lower().replace('_', ' ')} não encontrado(a).")
    return EscrituraLida(arquivo=documento.arquivo, campos=campos, pendencias=pendencias)
