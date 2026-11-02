"""Leituras comuns aos documentos registrais (matrícula e escritura): nomes e áreas.

Usam a linguagem padrão dos cartórios: "PROPRIETÁRIA: Fulano Ltda., inscrita...",
"OUTORGADO COMPRADOR: Fulano, brasileiro...", "com a área de 300,00 m² (trezentos metros
quadrados)". As posições são as do texto corrido (extracao/texto_corrido.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from arquiteto_auditor.dominio.numeros import encontrar_valores, numero_do_extenso
from arquiteto_auditor.extracao.texto_corrido import normalizar

_AREA = re.compile(r"AREA\s+(?:TOTAL\s+)?DE\s+")
_ABREVIACOES = ("LTDA", "CIA", "JR", "S/A", "S.A", "EIRELI", "ME", "EPP")


@dataclass(frozen=True)
class NomeLido:
    texto: str
    fim: int  # posição do fim do nome no texto
    limpo: bool  # sinais soltos do OCR foram removidos (o nome deve ser confirmado)


# Aspas e sinais soltos no começo ou no fim de uma palavra: sujeira de OCR, não parte do nome
# ("D'Ávila", com a aspa no meio da palavra, continua valendo).
_SINAIS_SOLTOS = re.compile(r"(?<!\w)['\"“”‘’`*|]+|['\"“”‘’`*|]+(?!\w)")


def ler_nome(plano: str, inicio: int) -> NomeLido | None:
    """Nome a partir de `inicio`, até a vírgula, o ponto-e-vírgula ou o fim da frase."""
    trecho = plano[inicio:inicio + 120]
    for m in re.finditer(r"[,;]|\.(?=\s|$)", trecho):
        if m.group() == ".":
            palavra = trecho[:m.start()].split()[-1:] or [""]
            if normalizar(palavra[0]).rstrip(".") in _ABREVIACOES:
                fim = m.end()  # "Ltda." faz parte do nome
                break
        fim = m.start()
        break
    else:
        return None
    bruto = " ".join(trecho[:fim].split())
    nome = " ".join(_SINAIS_SOLTOS.sub("", bruto).split())
    if not re.search(r"[A-Za-zÀ-ú]{2}", nome):
        return None
    return NomeLido(nome, inicio + fim, limpo=nome != bruto)


@dataclass(frozen=True)
class AreaLida:
    valor: float
    inicio: int  # trecho "área de N m²" (a evidência)
    fim: int
    inicio_numero: int  # só o número (a confiança do OCR vem daqui)
    fim_numero: int
    extenso: int | None  # parte inteira do valor por extenso, quando há


def ler_area(texto: str, normalizado: str, inicio: int, fim: int) -> AreaLida | None:
    """A primeira "área de N m² (extenso)" do trecho.

    Logo depois de "área de", uma medida em metros só pode ser o "m²" mal lido pelo OCR
    ("m?" vira "m"); por isso "m" também é aceito.
    """
    m = _AREA.search(normalizado, inicio, fim)
    if not m:
        return None
    for valor in encontrar_valores(texto[m.end():m.end() + 40]):
        if valor.unidade in ("m2", "m", None) and valor.valor > 0:
            depois = m.end() + valor.fim
            parenteses = re.match(r"[^(]{0,8}\(([^)]{3,160})\)", texto[depois:depois + 180])
            extenso = numero_do_extenso(parenteses.group(1)) if parenteses else None
            numero = m.end() + valor.inicio
            tamanho = len(re.match(r"[\d.,]+", valor.texto).group())
            return AreaLida(valor.valor, m.start(), depois, numero, numero + tamanho, extenso)
    return None
