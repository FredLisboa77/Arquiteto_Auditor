"""Cotas SEM rótulo na planta de situação: recuos, testada e profundidade (sem LLM).

Nos projetos reais, os recuos costumam ser cotas soltas, sem a palavra "recuo" (docs/06 §3).
Sem rótulo, a única pista segura é a forma do desenho:
1. CADEIA: três cotas alinhadas (na mesma fileira ou na mesma coluna) cujas partes somam uma
   cota paralela vizinha, o total. Na horizontal: lateral + edificação + lateral = testada; na
   vertical: frontal + edificação + fundos = profundidade do lote.
2. RUA: o texto com o nome da rua ("RUA", "AVENIDA", "ALAMEDA"...) perto das cadeias diz onde
   é a frente. Olhando da rua para o lote, a esquerda de quem olha é a lateral esquerda: com a
   rua embaixo na folha, é o lado esquerdo da folha; com a rua em cima, o direito.
Sem rua por perto, ou com a cadeia incompleta (cota omitida), nada é afirmado. Tudo o que sai
daqui é "pendente de confirmação": a associação é incerta por natureza (CLAUDE.md §3).

Também o muro sem rótulo: a cota girada mais próxima do texto "MURO" (pendente, idem).
"""

from __future__ import annotations

import re
import unicodedata
from itertools import combinations

from arquiteto_auditor.dominio.documento import OrigemPalavra, PaginaLida
from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    OrigemValor,
    StatusConfirmacao,
    ValorExtraido,
)
from arquiteto_auditor.dominio.numeros import encontrar_valores, ler_valor
from arquiteto_auditor.extracao.pranchas.linhas import LinhaTexto, agrupar_linhas, uniao_bbox

CONFIANCA_CADEIA = 0.6
CONFIANCA_MURO = 0.5
RAIO_RUA = 4  # a rua precisa estar a até 4× o tamanho da região das cadeias
TOLERANCIA_SOMA = 0.011  # m: as partes precisam somar o total (arredondamento de 2 casas)
_RUA = re.compile(r"\b(RUA|AVENIDA|AV|ALAMEDA|TRAVESSA|ESTRADA|RODOVIA)\b")
OBSERVACAO_CADEIA = ("Cota sem rótulo, identificada pela cadeia de cotas (as partes somam o "
                     "total) e pela posição da rua. Confirme.")
OBSERVACAO_MURO = "Cota sem rótulo mais próxima do texto \"MURO\". Confirme."


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.upper())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _so_cota(linha: LinhaTexto) -> float | None:
    """Valor de uma linha que é só uma medida em metros ("6,00", "12.97", "1,80 m")."""
    lido = ler_valor(linha.texto)
    if lido is None or lido.unidade not in ("m", None) or lido.valor <= 0:
        return None
    return lido.valor


def _ao_longo(linha: LinhaTexto) -> float:
    """Posição ao longo da cadeia: x no texto deitado, y no texto girado."""
    x0, y0, x1, y1 = linha.bbox
    return (y0 + y1) / 2 if linha.vertical else (x0 + x1) / 2


def _atravessado(linha: LinhaTexto) -> float:
    """Posição de lado (a fileira ou a coluna da cadeia)."""
    x0, y0, x1, y1 = linha.bbox
    return (x0 + x1) / 2 if linha.vertical else (y0 + y1) / 2


def _cadeias(cotas: list[tuple[LinhaTexto, float]], vertical: bool):
    """(três partes em ordem ao longo, total) para cada cadeia que fecha a soma."""
    da_orientacao = [(ln, v) for ln, v in cotas if ln.vertical == vertical]
    achadas = []
    for a, b, c in combinations(sorted(da_orientacao, key=lambda i: _ao_longo(i[0])), 3):
        altura = max(a[0].altura, b[0].altura, c[0].altura)
        if max(_atravessado(x[0]) for x in (a, b, c)) - min(
                _atravessado(x[0]) for x in (a, b, c)) > 0.5 * altura:
            continue  # não estão na mesma fileira/coluna
        entre = [x for x in da_orientacao if x not in (a, b, c)
                 and abs(_atravessado(x[0]) - _atravessado(a[0])) <= 0.5 * altura
                 and _ao_longo(a[0]) < _ao_longo(x[0]) < _ao_longo(c[0])]
        if entre:
            continue  # partes não consecutivas
        soma = a[1] + b[1] + c[1]
        for total in da_orientacao:
            if (total[0] not in (a[0], b[0], c[0])
                    and abs(total[1] - soma) <= TOLERANCIA_SOMA
                    and 0 < abs(_atravessado(total[0]) - _atravessado(a[0])) <= 4 * altura
                    and _ao_longo(a[0]) < _ao_longo(total[0]) < _ao_longo(c[0])):
                achadas.append(((a, b, c), total))
                break
    return achadas


def _distancia(c1, c2) -> float:
    dx = max(c1[0] - c2[2], c2[0] - c1[2], 0)
    dy = max(c1[1] - c2[3], c2[1] - c1[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def _valor(campo, linha: LinhaTexto, valor: float, pagina: PaginaLida, arquivo: str,
           confianca: float, observacao: str) -> ValorExtraido:
    ocr = any(p.origem == OrigemPalavra.OCR for p in linha.palavras)
    return ValorExtraido(
        campo=campo, valor=valor, unidade="m",
        origem=OrigemValor.OCR if ocr else OrigemValor.VETORIAL,
        confianca=round(confianca * (linha.confianca if ocr else 1.0), 3),
        status=StatusConfirmacao.PENDENTE, observacao=observacao,
        evidencias=[Evidencia(documento=arquivo, pagina=pagina.numero, trecho=linha.texto,
                              bbox=linha.bbox,
                              confianca_ocr=linha.confianca if ocr else None)])


def _ler_cadeias(linhas, cotas, pagina, arquivo) -> list[ValorExtraido]:
    horizontais, verticais = _cadeias(cotas, False), _cadeias(cotas, True)
    if not horizontais and not verticais:
        return []
    regiao = uniao_bbox([x[0].bbox for partes, total in horizontais + verticais
                         for x in (*partes, total)])
    tamanho = max(regiao[2] - regiao[0], regiao[3] - regiao[1])
    ruas = [ln for ln in linhas if not ln.vertical and _RUA.search(_normalizar(ln.texto))
            and _distancia(ln.bbox, regiao) <= RAIO_RUA * tamanho]
    if not ruas:
        return []
    rua = min(ruas, key=lambda ln: _distancia(ln.bbox, regiao))

    valores = []
    for (a, _, c), total in horizontais[:1]:
        rua_embaixo = rua.centro_y > _atravessado(a[0])
        esquerda, direita = (a, c) if rua_embaixo else (c, a)
        for campo, (linha, valor) in (("RECUO_LATERAL_E", esquerda),
                                      ("RECUO_LATERAL_D", direita),
                                      ("TERRENO_TESTADA", total)):
            valores.append(_valor(campo, linha, valor, pagina, arquivo, CONFIANCA_CADEIA,
                                  OBSERVACAO_CADEIA))
    for (a, b, c), total in verticais[:1]:
        rua_embaixo = rua.centro_y > _ao_longo(b[0])
        frente, fundos = (c, a) if rua_embaixo else (a, c)  # y cresce para baixo na folha
        for campo, (linha, valor) in (("RECUO_FRONTAL", frente), ("RECUO_FUNDOS", fundos),
                                      ("TERRENO_PROFUNDIDADE", total)):
            valores.append(_valor(campo, linha, valor, pagina, arquivo, CONFIANCA_CADEIA,
                                  OBSERVACAO_CADEIA))
    return valores


def _ler_muro(linhas, cotas, pagina, arquivo) -> list[ValorExtraido]:
    normalizadas = [(ln, _normalizar(ln.texto)) for ln in linhas]
    if any("MURO" in t and encontrar_valores(ln.texto) for ln, t in normalizadas):
        return []  # há cota de muro com rótulo: quadro.py já leu
    valores = []
    for rotulo, texto in normalizadas:
        if rotulo.vertical or texto.strip(" .:") != "MURO":
            continue
        perto = [(ln, v) for ln, v in cotas if ln.vertical
                 and _distancia(ln.bbox, rotulo.bbox) <= 10 * rotulo.altura]
        if perto:
            linha, valor = min(perto, key=lambda i: _distancia(i[0].bbox, rotulo.bbox))
            valores.append(_valor("MURO_ALTURA", linha, valor, pagina, arquivo,
                                  CONFIANCA_MURO, OBSERVACAO_MURO))
    return valores


def ler_cotas_sem_rotulo(pagina: PaginaLida, arquivo: str) -> list[ValorExtraido]:
    linhas = agrupar_linhas(pagina.palavras)
    cotas = [(ln, v) for ln in linhas if (v := _so_cota(ln)) is not None]
    return (_ler_cadeias(linhas, cotas, pagina, arquivo)
            + _ler_muro(linhas, cotas, pagina, arquivo))
