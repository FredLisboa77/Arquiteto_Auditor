"""Leitura do quadro de áreas e das cotas com rótulo das pranchas (sem LLM).

Os quadros reais e sintéticos variam muito (docs/06 §1 e §2): tabela, texto com pontilhado,
células com o rótulo em cima, valor antes do rótulo, vários índices numa linha só
("T.O. = 30%   C.A. = 0,54") e o estilo AutoCAD ("A=119.97m²", rótulo quebrado em duas linhas:
"TAXA DE" / "OCUPAÇÃO"). Por isso a leitura procura RÓTULOS conhecidos dentro das linhas de
texto e, para cada um, o valor:
1. na mesma linha (o primeiro valor depois do rótulo; se não houver, o mais próximo antes);
2. senão, numa linha vizinha que seja SÓ um valor: à direita, à esquerda ou logo abaixo.
A unidade precisa combinar com o campo (área em m², taxa em %, altura em m): "29,99 m²" ao
lado de "Taxa de ocupação" é descartado. Números são lidos só pelo normalizador único.

Cotas com rótulo ("RECUO FRONTAL 6,00", "MURO H=1.80m", inclusive giradas 90°) usam a mesma
leitura, mas só aceitam o valor na MESMA linha: um rótulo de cota solto (ex.: "MURO" escrito
sobre o desenho) não puxa um número vizinho qualquer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from arquiteto_auditor.dominio.documento import OrigemPalavra, PaginaLida
from arquiteto_auditor.dominio.modelos import Evidencia, OrigemValor, ValorExtraido
from arquiteto_auditor.dominio.numeros import ValorLido, encontrar_valores, ler_valor
from arquiteto_auditor.extracao.pranchas.linhas import LinhaTexto, agrupar_linhas, uniao_bbox

# campo → (rótulos normalizados, unidades aceitas, unidade gravada)
_AREA = ({"m2", None}, "m2")
_TAXA = ({"%", None}, "%")
ROTULOS_QUADRO: dict[str, tuple[tuple[str, ...], set, str | None]] = {
    "TERRENO_AREA": (("AREA DO TERRENO", "AREA DO LOTE", "AREA TERRENO"), *_AREA),
    "AREA_CONSTR_PAV_1": (("AREA CONSTRUIDA TERREO", "AREA COBERTA TERREO", "AREA DO TERREO",
                           "PAVIMENTO TERREO", "PAV TERREO", "AREA CONSTRUIDA PAV TERREO"),
                          *_AREA),
    "AREA_CONSTR_PAV_2": (("AREA CONSTRUIDA PAV SUPERIOR", "AREA CONSTRUIDA PAVIMENTO SUPERIOR",
                           "AREA 1 PAVIMENTO", "AREA DO 1 PAVIMENTO", "PAVIMENTO SUPERIOR",
                           "PAV SUPERIOR", "AREA PAV SUPERIOR", "AREA CONSTRUIDA SUPERIOR"),
                          *_AREA),
    "AREA_CONSTR_TOTAL": (("AREA CONSTRUIDA TOTAL", "AREA TOTAL CONSTRUIDA",
                           "TOTAL CONSTRUIDO", "AREA TOTAL DE CONSTRUCAO"), *_AREA),
    "AREA_PROJECAO": (("AREA DE PROJECAO", "PROJECAO", "AREA PROJETADA"), *_AREA),
    "AREA_PERMEAVEL": (("AREA PERMEAVEL",), *_AREA),
    "TO_DECLARADA": (("TAXA DE OCUPACAO", "INDICE DE OCUPACAO", "T O"), *_TAXA),
    "CA_DECLARADO": (("COEFICIENTE DE APROVEITAMENTO", "INDICE DE APROVEITAMENTO", "C A"),
                     {None}, None),
    "PERMEAVEL_DECLARADA": (("TAXA DE PERMEABILIDADE", "INDICE DE PERMEABILIDADE", "T P"),
                            *_TAXA),
    "ALTURA": (("ALTURA DA EDIFICACAO", "ALTURA TOTAL", "ALTURA DA CONSTRUCAO"), {"m", None},
               "m"),
    # cotas com rótulo (só valor na mesma linha — ver SO_NA_MESMA_LINHA)
    "TERRENO_TESTADA": (("TESTADA", "TESTADA DO LOTE", "FRENTE DO LOTE"), {"m", None}, "m"),
    "TERRENO_PROFUNDIDADE": (("PROFUNDIDADE", "PROFUNDIDADE DO LOTE"), {"m", None}, "m"),
    "RECUO_FRONTAL": (("RECUO FRONTAL", "RECUO DE FRENTE", "AFASTAMENTO FRONTAL"), {"m", None},
                      "m"),
    "RECUO_FUNDOS": (("RECUO DE FUNDOS", "RECUO FUNDOS", "AFASTAMENTO DE FUNDOS"), {"m", None},
                     "m"),
    "RECUO_LATERAL_E": (("LATERAL ESQ", "LATERAL ESQUERDA", "LATERAL ESQUERDO",
                         "RECUO LATERAL ESQ", "RECUO LATERAL ESQUERDO",
                         "AFASTAMENTO LATERAL ESQUERDO"), {"m", None}, "m"),
    "RECUO_LATERAL_D": (("LATERAL DIR", "LATERAL DIREITA", "LATERAL DIREITO",
                         "RECUO LATERAL DIR", "RECUO LATERAL DIREITO",
                         "AFASTAMENTO LATERAL DIREITO"), {"m", None}, "m"),
    "MURO_ALTURA": (("MURO", "MURO DE DIVISA", "MURO FRONTAL", "MURO DE FECHAMENTO",
                     "ALTURA DO MURO"), {"m", None}, "m"),
}
SO_NA_MESMA_LINHA = {"TERRENO_TESTADA", "TERRENO_PROFUNDIDADE", "RECUO_FRONTAL", "RECUO_FUNDOS",
                     "RECUO_LATERAL_E", "RECUO_LATERAL_D", "MURO_ALTURA"}
_PADROES = [
    (campo, re.compile(r"(?<![A-Z0-9])" + r"\s+".join(rotulo.split()) + r"(?![A-Z0-9])"))
    for campo, (rotulos, _, _) in ROTULOS_QUADRO.items() for rotulo in rotulos
]
_PREFIXO_CAD = re.compile(r"^\s*[A-Za-z]\s*=\s*")  # "A=", "C=", "H=" (docs/06 §2)
_PREFIXO_CAD_NO_MEIO = re.compile(r"(?<![^\W\d_])[A-Za-z]\s*=")  # "MURO H=1.80m"
CONFIANCA = {"mesma linha": 0.9, "direita": 0.9, "esquerda": 0.85, "abaixo": 0.85}


@dataclass(frozen=True)
class _Rotulo:
    campo: str
    inicio: int
    fim: int


def _normalizar(texto: str) -> str:
    """Maiúsculas, sem acentos e sem pontuação, COM o mesmo tamanho (as posições valem)."""
    saida = []
    for c in texto:
        base = unicodedata.normalize("NFD", c)[0].upper()
        saida.append(" " if base in ".:º°ª=" or len(base) != 1 else base)
    return "".join(saida)


def _rotulos(texto: str) -> list[_Rotulo]:
    """Rótulos do quadro dentro de um texto; sobreposição → fica o mais longo."""
    normalizado = _normalizar(texto)
    achados = sorted((_Rotulo(campo, m.start(), m.end())
                      for campo, padrao in _PADROES for m in padrao.finditer(normalizado)),
                     key=lambda r: (r.inicio - r.fim, r.inicio))
    escolhidos: list[_Rotulo] = []
    for r in achados:
        if all(r.fim <= e.inicio or r.inicio >= e.fim for e in escolhidos):
            escolhidos.append(r)
    return sorted(escolhidos, key=lambda r: r.inicio)


def _linha_de_quadro(texto: str, rotulos: list[_Rotulo]) -> bool:
    """Linha de quadro = só rótulos, valores e pontuação (pontilhado, "=", "—").

    Sobrou outra palavra → é título ou texto do desenho que contém palavras de um rótulo
    ("PLANTA BAIXA — PAVIMENTO SUPERIOR — ESCALA 1:100", "ÁREA PERMEÁVEL (GRAMA)").
    """
    resto = list(_PREFIXO_CAD_NO_MEIO.sub(lambda m: " " * len(m.group(0)), texto))
    for inicio, fim in [(r.inicio, r.fim) for r in rotulos] + [
            (v.inicio, v.fim) for v in encontrar_valores(texto)]:
        resto[inicio:fim] = " " * (fim - inicio)
    return not re.search(r"[^\W\d_]", "".join(resto))  # nenhuma letra sobrando


def _so_valor(linha: LinhaTexto) -> ValorLido | None:
    """O valor, se a linha for só um valor ("400,00 m²", "A=119.97m²", "C=0.54")."""
    return ler_valor(_PREFIXO_CAD.sub("", linha.texto))


def _unidade_ok(campo: str, valor: ValorLido) -> bool:
    return valor.unidade in ROTULOS_QUADRO[campo][1]


def _valores_na_linha(texto: str, rotulos: list[_Rotulo]) -> dict[int, ValorLido]:
    """Índice do rótulo → valor na mesma linha (depois dele; senão, o mais próximo antes)."""
    valores = encontrar_valores(texto)
    usados: set[int] = set()
    resultado: dict[int, ValorLido] = {}
    for i, r in enumerate(rotulos):
        proximo = rotulos[i + 1].inicio if i + 1 < len(rotulos) else len(texto)
        anterior = rotulos[i - 1].fim if i > 0 else 0
        depois = [v for v in valores if r.fim <= v.inicio < proximo]
        antes = [v for v in valores if anterior <= v.inicio and v.fim <= r.inicio]
        for v in depois[:1] or antes[-1:]:
            if id(v) not in usados and _unidade_ok(r.campo, v):
                usados.add(id(v))
                resultado[i] = v
    return resultado


def _vizinho(linha: LinhaTexto, linhas: list[LinhaTexto]) -> tuple[LinhaTexto, str] | None:
    """Linha vizinha que seja só um valor: à direita, à esquerda ou logo abaixo."""
    altura = linha.altura
    linhas = [ln for ln in linhas if not ln.vertical]  # direita/abaixo só no texto deitado
    mesma_fileira = [ln for ln in linhas if ln is not linha and
                     abs(ln.centro_y - linha.centro_y) <= 0.6 * max(altura, ln.altura)]
    direita = [ln for ln in mesma_fileira if ln.bbox[0] > linha.bbox[2]]
    esquerda = [ln for ln in mesma_fileira if ln.bbox[2] < linha.bbox[0]]
    abaixo = [ln for ln in linhas if ln.bbox[1] >= linha.bbox[3] - 0.2 * altura
              and ln.bbox[1] - linha.bbox[3] <= 3 * altura
              and abs(ln.bbox[0] - linha.bbox[0]) <= 2 * altura]
    candidatos = (
        (min(direita, key=lambda ln: ln.bbox[0]) if direita else None, "direita"),
        (max(esquerda, key=lambda ln: ln.bbox[2]) if esquerda else None, "esquerda"),
        (min(abaixo, key=lambda ln: ln.bbox[1]) if abaixo else None, "abaixo"),
    )
    for candidato, lado in candidatos:
        if candidato is not None and _so_valor(candidato) is not None:
            return candidato, lado
    return None


def _complemento(linha: LinhaTexto, linhas: list[LinhaTexto]) -> LinhaTexto | None:
    """Linha logo abaixo que continua um rótulo quebrado ("TAXA DE" / "OCUPAÇÃO")."""
    abaixo = [ln for ln in linhas if 0 <= ln.bbox[1] - linha.bbox[3] <= 1.5 * linha.altura
              and abs(ln.bbox[0] - linha.bbox[0]) <= linha.altura
              and not encontrar_valores(ln.texto)]
    return min(abaixo, key=lambda ln: ln.bbox[1]) if abaixo else None


def ler_quadro_areas(pagina: PaginaLida, arquivo: str) -> list[ValorExtraido]:
    linhas = agrupar_linhas(pagina.palavras)
    consumidas: set[int] = set()  # complementos de rótulo quebrado já usados
    resultado: list[ValorExtraido] = []
    for linha in linhas:
        if id(linha) in consumidas:
            continue
        rotulos, partes = _rotulos(linha.texto), [linha]
        if not rotulos and (complemento := _complemento(linha, linhas)) is not None:
            juntos = [r for r in _rotulos(f"{linha.texto} {complemento.texto}")
                      if r.inicio < len(linha.texto)]
            if juntos:
                rotulos, partes = juntos, [linha, complemento]
                consumidas.add(id(complemento))
        if not rotulos or not _linha_de_quadro(" ".join(ln.texto for ln in partes),
                                                rotulos):
            continue
        na_linha = _valores_na_linha(linha.texto, rotulos)
        for i, rotulo in enumerate(rotulos):
            fonte, como, valor = linha, "mesma linha", na_linha.get(i)
            if (valor is None and len(rotulos) == 1 and not encontrar_valores(linha.texto)
                    and rotulo.campo not in SO_NA_MESMA_LINHA and not linha.vertical):
                vizinho = _vizinho(linha, linhas)
                if vizinho is not None:
                    fonte, como = vizinho
                    valor = _so_valor(fonte)
            if valor is None or not _unidade_ok(rotulo.campo, valor):
                continue
            resultado.append(_montar(rotulo.campo, valor, partes, fonte, como, pagina, arquivo))
    return resultado


def _montar(campo: str, valor: ValorLido, partes: list[LinhaTexto], fonte: LinhaTexto,
            como: str, pagina: PaginaLida, arquivo: str) -> ValorExtraido:
    envolvidas = partes + ([fonte] if fonte not in partes else [])
    palavras = [p for ln in envolvidas for p in ln.palavras]
    ocr = any(p.origem == OrigemPalavra.OCR for p in palavras)
    confianca_ocr = min(p.confianca for p in palavras) if ocr else None
    trecho = " ".join(ln.texto for ln in partes)
    if fonte not in partes:
        trecho = f"{trecho} {fonte.texto}"
    return ValorExtraido(
        campo=campo, valor=valor.valor, unidade=ROTULOS_QUADRO[campo][2],
        origem=OrigemValor.OCR if ocr else OrigemValor.VETORIAL,
        confianca=round(CONFIANCA[como] * (confianca_ocr or 1.0), 3),
        evidencias=[Evidencia(documento=arquivo, pagina=pagina.numero, trecho=trecho,
                              bbox=uniao_bbox([ln.bbox for ln in envolvidas]),
                              confianca_ocr=confianca_ocr)])
