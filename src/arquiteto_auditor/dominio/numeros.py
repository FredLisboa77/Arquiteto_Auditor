"""Leitura de números e unidades no formato brasileiro.

Este é o ÚNICO lugar do sistema que transforma texto em número (regra do CLAUDE.md).
Exemplos aceitos: "1.234,56 m²", "5,00m", "60 %", "-0,15", "2 (dois) pavimentos",
"dois pavimentos", "R$ 1.000,00".

Duas funções principais:
- `ler_valor(texto)`: o texto inteiro deve ser UM valor (ex.: célula do quadro de áreas).
- `encontrar_valores(texto)`: acha todos os valores numéricos dentro de uma frase.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ValorLido:
    valor: float
    unidade: str | None  # "m", "m2", "%", "pavimentos", "R$" ou None
    texto: str  # trecho original, exatamente como aparece no documento
    inicio: int  # posição do trecho no texto analisado
    fim: int
    ambiguo: bool = False  # ex.: "1.500" (mil e quinhentos ou 1,5?)
    extenso_divergente: bool = False  # ex.: "60% (cinquenta por cento)"


# ---------------------------------------------------------------- expressões regulares

_NUMERO = r"""
    (?<![\w.,/-])                         # não pode estar colado em letra/código (ZR2, R-1)
    (?P<sinal>[+-])?
    (?P<numero>
        \d{1,3}(?:\.\d{3})+(?:,\d+)?      # com ponto de milhar: 1.234 / 1.234,56
      | \d+\.\d{1,2}(?![\d.])             # ponto decimal do CAD: 5.00 / 2.5
      | \d+(?:,\d+)?                      # simples: 450 / 450,00
    )
    (?!\d)
"""

_UNIDADE = r"""
    (?P<unidade>
        m²|m2(?!\d)|m\^2|metros?\s+quadrados?
      | cm\b
      | metros?\b|mts?\b|m\b
      | %
      | pavimentos?\b
    )
"""

_PADRAO_VALOR = re.compile(
    rf"""
    (?P<moeda>R\$\s*)?
    {_NUMERO}
    (?:\s*{_UNIDADE})?
    (?:\s*\((?P<extenso>[^)]{{1,120}})\))?
    (?:\s*(?P<unidade_depois>pavimentos?\b))?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _normalizar_unidade(bruta: str | None) -> str | None:
    if not bruta:
        return None
    u = bruta.lower()
    if u in ("m²", "m2", "m^2") or "quadrado" in u:
        return "m2"
    if u == "cm":
        return "cm"
    if u in ("m", "mt", "mts", "metro", "metros"):
        return "m"
    if u == "%":
        return "%"
    if u.startswith("pavimento"):
        return "pavimentos"
    return None


def _converter_numero(numero: str) -> tuple[float, bool]:
    """Converte a parte numérica. Retorna (valor, ambiguo)."""
    if "," in numero:
        return float(numero.replace(".", "").replace(",", ".")), False
    if re.fullmatch(r"\d+\.\d{1,2}", numero):
        return float(numero), False
    if "." in numero:
        grupos = numero.split(".")
        # Um único grupo de milhar sem vírgula ("1.500") é ambíguo.
        return float(numero.replace(".", "")), len(grupos) == 2
    return float(numero), False


def _montar(m: re.Match, deslocamento: int = 0) -> ValorLido:
    valor, ambiguo = _converter_numero(m.group("numero"))
    if m.group("sinal") == "-":
        valor = -valor
    unidade = _normalizar_unidade(m.group("unidade") or m.group("unidade_depois"))
    if m.group("moeda"):
        unidade = "R$"
    if unidade == "cm":
        valor, unidade = valor / 100, "m"

    divergente = False
    if m.group("extenso"):
        numero_extenso = _numero_no_extenso(m.group("extenso"))
        if numero_extenso is not None and numero_extenso != int(abs(valor)):
            divergente = True

    return ValorLido(
        valor=valor,
        unidade=unidade,
        texto=m.group(0).strip(),
        inicio=m.start() + deslocamento,
        fim=m.start() + deslocamento + len(m.group(0).rstrip()),
        ambiguo=ambiguo,
        extenso_divergente=divergente,
    )


def encontrar_valores(texto: str) -> list[ValorLido]:
    """Todos os valores numéricos de uma frase, com posição e unidade."""
    return [_montar(m) for m in _PADRAO_VALOR.finditer(texto)]


def ler_valor(texto: str) -> ValorLido | None:
    """Lê um texto que deve conter exatamente UM valor; senão retorna None."""
    limpo = texto.strip()
    deslocamento = texto.find(limpo) if limpo else 0
    prefixo = re.match(r"[=:]\s*", limpo)
    if prefixo:
        deslocamento += prefixo.end()
        limpo = limpo[prefixo.end() :]
    if not limpo:
        return None

    m = _PADRAO_VALOR.fullmatch(limpo)
    if m:
        return _montar(m, deslocamento)
    return _ler_valor_so_por_extenso(limpo, deslocamento)


# ---------------------------------------------------------------- números por extenso

_UNIDADES = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11,
    "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14, "quinze": 15,
    "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19,
}
_DEZENAS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
    "setenta": 70, "oitenta": 80, "noventa": 90,
}
_CENTENAS = {
    "cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300,
    "trezentas": 300, "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500,
    "quinhentas": 500, "seiscentos": 600, "seiscentas": 600, "setecentos": 700,
    "setecentas": 700, "oitocentos": 800, "oitocentas": 800, "novecentos": 900,
    "novecentas": 900,
}
_PALAVRAS_NUMERO = _UNIDADES | _DEZENAS | _CENTENAS

_PALAVRAS_DE_UNIDADE = ("por cento", "metros", "metro", "pavimentos", "pavimento", "reais")


def _sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def ler_extenso(texto: str) -> int | None:
    """Converte um número inteiro escrito por extenso ("quatrocentos e cinquenta" → 450)."""
    palavras = _sem_acentos(texto).split()
    if not palavras or palavras[0] == "e" or palavras[-1] == "e":
        return None

    total, atual, viu_mil, anterior_numero = 0, 0, False, False
    for palavra in palavras:
        if palavra == "e":
            if not anterior_numero:
                return None
            anterior_numero = False
            continue
        if palavra == "mil":
            if viu_mil:
                return None
            total += (atual or 1) * 1000
            atual, viu_mil = 0, True
        elif palavra in _PALAVRAS_NUMERO:
            atual += _PALAVRAS_NUMERO[palavra]
        else:
            return None
        anterior_numero = True
    return total + atual


def _numero_no_extenso(extenso: str) -> int | None:
    """Parte numérica de um extenso entre parênteses: "cinquenta por cento" → 50."""
    texto = _sem_acentos(extenso)
    corte = len(texto)
    for palavra in _PALAVRAS_DE_UNIDADE:
        posicao = texto.find(palavra)
        if posicao != -1:
            corte = min(corte, posicao)
    return ler_extenso(texto[:corte])


def _ler_valor_so_por_extenso(texto: str, deslocamento: int) -> ValorLido | None:
    """Ex.: "dois pavimentos" — número por extenso seguido de unidade conhecida."""
    palavras = texto.split()
    for corte in range(len(palavras), 0, -1):
        numero = ler_extenso(" ".join(palavras[:corte]))
        if numero is None:
            continue
        resto = " ".join(palavras[corte:])
        unidade = _normalizar_unidade(resto) if resto else None
        if resto and unidade is None:
            return None
        return ValorLido(
            valor=float(numero),
            unidade=unidade,
            texto=texto,
            inicio=deslocamento,
            fim=deslocamento + len(texto),
        )
    return None
