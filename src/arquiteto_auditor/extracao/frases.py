"""Valores escritos em frases ("o terreno possui área de 400,00 m²"), sem LLM.

Memoriais trazem parte dos números em texto corrido (docs/06 §6.2). Cada campo tem uma
expressão que termina logo antes do número; o número precisa vir em seguida (até alguns
caracteres), com a unidade certa. Para não confundir com as especificações técnicas (piscina
com "área de 24,00 m²", "profundidade de 1,40 m", pé-direito...), terreno, testada e
profundidade só valem numa frase que fala do TERRENO.
Valor lido por OCR com baixa confiança fica pendente de confirmação.
"""

from __future__ import annotations

import re

from arquiteto_auditor.config import limiar_confianca_ocr
from arquiteto_auditor.dominio.modelos import OrigemValor, StatusConfirmacao, ValorExtraido
from arquiteto_auditor.dominio.numeros import encontrar_valores
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido, normalizar

CONFIANCA = 0.85
ALCANCE = 25  # caracteres entre o fim da expressão e o número

_AREA = ({"m2", "m", None}, "m2")  # "m" = "m²" mal lido pelo OCR
_METROS = ({"m", None}, "m")
_TAXA = ({"%", None}, "%")
_LIGACAO = r"(?:E\s+)?(?:DE\s+)?"  # "é de", "de", "é"

# campo → (expressão que termina antes do número, unidades aceitas, unidade gravada)
FRASES: dict[str, tuple[str, set, str | None]] = {
    "TERRENO_AREA": (r"\bTERRENO\b[^.;]{0,60}?\bAREA\s+DE\s+", *_AREA),
    "TERRENO_TESTADA": (r"\bTERRENO\b[^.]{0,160}?\bTESTADA\s+DE\s+", *_METROS),
    "TERRENO_PROFUNDIDADE": (r"\bTERRENO\b[^.]{0,200}?\bPROFUNDIDADE\s+DE\s+", *_METROS),
    "AREA_CONSTR_TOTAL": (rf"\bAREA\s+CONSTRUIDA\s+TOTAL\s+{_LIGACAO}", *_AREA),
    "AREA_PERMEAVEL": (rf"\bAREA\s+PERMEAVEL\s+{_LIGACAO}", *_AREA),
    "PERMEAVEL_DECLARADA": (rf"\bTAXA\s+DE\s+PERMEABILIDADE\s+{_LIGACAO}", *_TAXA),
    "TO_DECLARADA": (rf"\bTAXA\s+DE\s+OCUPACAO\s+{_LIGACAO}", *_TAXA),
    "CA_DECLARADO": (rf"\bCOEFICIENTE\s+DE\s+APROVEITAMENTO\s+{_LIGACAO}", {None}, None),
    "ALTURA": (r"\bALTURA\s+TOTAL\b[^.;]{0,120}?\b(?:E\s+DE|DE|E)\s+", *_METROS),
    "MURO_ALTURA": (r"\bMURO\b[^.;]{0,40}?\bALTURA\s+DE\s+", *_METROS),
}
# Número ANTES das palavras: "totalizando 6,50 m de altura"
_DEPOIS_DO_NUMERO = {"ALTURA": r"^\s*DE\s+ALTURA\b"}


def ler_frases(corrido: TextoCorrido, arquivo: str) -> list[ValorExtraido]:
    plano = corrido.texto.replace("\n", " ")  # mesmo tamanho: as posições valem
    normalizado = normalizar(plano)
    achados: list[tuple[str, int, int, int, int]] = []  # campo, trecho, número
    for campo, (expressao, unidades, _) in FRASES.items():
        for m in re.finditer(expressao, normalizado):
            for valor in encontrar_valores(plano[m.end():m.end() + ALCANCE + 20]):
                if valor.inicio > ALCANCE:
                    break
                if valor.unidade in unidades:
                    numero = m.end() + valor.inicio
                    achados.append((campo, m.start(), m.end() + valor.fim, numero,
                                    numero + len(valor.texto)))
                break  # só o primeiro número depois da expressão
    for campo, expressao in _DEPOIS_DO_NUMERO.items():
        for valor in encontrar_valores(plano):
            if valor.unidade in FRASES[campo][1] and re.match(
                    expressao, normalizado[valor.fim:valor.fim + 20]):
                fim = valor.fim + re.match(expressao, normalizado[valor.fim:]).end()
                achados.append((campo, valor.inicio, fim, valor.inicio, valor.fim))

    resultado = []
    for campo, inicio, fim, inicio_numero, fim_numero in achados:
        valor = encontrar_valores(plano[inicio_numero:fim_numero])[0]
        evidencia = corrido.evidencia(inicio, fim, arquivo)
        ocr = corrido.confianca(inicio_numero, fim_numero)
        evidencia = evidencia.model_copy(update={"confianca_ocr": ocr})
        baixa = ocr is not None and ocr < limiar_confianca_ocr()
        resultado.append(ValorExtraido(
            campo=campo, valor=valor.valor, unidade=FRASES[campo][2],
            origem=OrigemValor.OCR if ocr is not None else OrigemValor.VETORIAL,
            confianca=round(CONFIANCA * (ocr if ocr is not None else 1.0), 3),
            evidencias=[evidencia],
            status=StatusConfirmacao.PENDENTE if baixa else StatusConfirmacao.AUTOMATICO,
            observacao=f"Confirme: leitura (OCR) com baixa confiança ({ocr:.2f})."
            if baixa else None))
    return resultado
