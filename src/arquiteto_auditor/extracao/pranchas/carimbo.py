"""Leitura do carimbo das pranchas: rótulo → valor, pela posição (sem LLM).

1. As palavras da página viram linhas de texto (linhas.py).
2. Uma linha é RÓTULO quando é exatamente um rótulo conhecido ("PROPRIETÁRIO:", "Rev.") ou
   começa com "rótulo:" seguido do valor ("Proprietário: João"). Assim um valor como
   "Condomínio Dias" não é confundido com o rótulo "Condomínio".
3. O valor é a linha à direita, na mesma altura; se não houver (ou se for outro rótulo), a
   linha logo abaixo, alinhada à esquerda com o rótulo (carimbos com o rótulo em cima).
   Rótulo seguido de outro rótulo = campo em branco (ex.: revisão não informada).
4. Campos compostos são separados ("19 / H" → lote e quadra; "71.677 — 3º Ofício..." →
   matrícula e cartório). O CPF nunca é guardado, nem na evidência (LGPD, CLAUDE.md §2).
"""

from __future__ import annotations

import re
import unicodedata

from arquiteto_auditor.dominio.documento import OrigemPalavra, PaginaLida, Palavra
from arquiteto_auditor.dominio.modelos import Evidencia, OrigemValor, ValorExtraido
from arquiteto_auditor.extracao.pranchas.linhas import (
    LinhaTexto,
    agrupar_linhas,
    uniao_bbox,
)

# Rótulos comuns de carimbos brasileiros, já normalizados (ver _normalizar).
# "LOTE_QUADRA" é composto; None = rótulo conhecido que não é extraído aqui (mas delimita).
ROTULOS: dict[str | None, tuple[str, ...]] = {
    "TITULO": ("PROJETO", "OBRA", "TITULO", "TITULO DO PROJETO", "NOME DO PROJETO"),
    "ENDERECO": ("ENDERECO", "ENDERECO DA OBRA", "LOCAL", "LOCALIZACAO", "LOGRADOURO"),
    "CONDOMINIO": ("CONDOMINIO", "LOTEAMENTO"),
    "LOTE_QUADRA": ("LOTE / QUADRA", "LOTE E QUADRA", "LOTE - QUADRA"),
    "LOTE": ("LOTE",),
    "QUADRA": ("QUADRA",),
    "MUNICIPIO": ("MUNICIPIO", "CIDADE", "MUNICIPIO / UF", "CIDADE / UF"),
    "MATRICULA": ("MATRICULA", "N MAT", "N MATRICULA", "MATRICULA N", "N DA MATRICULA"),
    "CARTORIO": ("CARTORIO", "CRI", "REGISTRO DE IMOVEIS"),
    "PROPRIETARIO": ("PROPRIETARIO", "PROPRIETARIA", "PROPRIETARIOS", "INTERESSADO",
                     "INTERESSADA", "REQUERENTE", "CONTRATANTE", "CLIENTE"),
    "AUTOR": ("AUTOR DO PROJETO", "AUTOR", "AUTORA", "RESP TECNICO", "RESPONSAVEL TECNICO",
              "RESPONSAVEL PELO PROJETO", "ARQUITETO", "ARQUITETA", "PROJETISTA"),
    "AUTOR_REGISTRO": ("REGISTRO", "REG PROF", "REGISTRO PROFISSIONAL", "CAU", "CREA",
                       "CAU / CREA", "N CAU"),
    "RRT": ("RRT", "RRT N", "N RRT", "ART", "ART N", "RRT / ART"),
    "REVISAO": ("REVISAO", "REV"),
    None: ("ESCRITORIO", "CONTEUDO", "PRANCHA", "FOLHA", "ESCALA", "DATA", "DESENHO",
           "DESENHISTA", "ASSUNTO", "FASE", "ETAPA", "ASSINATURA"),
}
_CAMPO_DO_ROTULO = {rotulo: campo for campo, rotulos in ROTULOS.items() for rotulo in rotulos}

DISTANCIA_DIREITA = 25  # em alturas de letra: até onde procurar o valor à direita
DISTANCIA_ABAIXO = 12  # em alturas de letra (células altas); para no primeiro texto abaixo
CONFIANCA = {"mesma linha": 0.95, "direita": 0.95, "abaixo": 0.9}

_CPF = re.compile(r"\s*[—–-]?\s*\bCPF\b.*$|\d{3}\.\d{3}\.\d{3}-\d{2}", re.IGNORECASE)
# "71.677 — 3º Ofício..." ou "nº 71.677 do 3º Ofício..."
_MATRICULA = re.compile(
    r"^\s*(?:[Nn][º°o.]?\s*)?(\d[\d.]*\d|\d)\s*(?:(?:[—–-]|\bd[oa]\b|\bn[oa]\b)\s*(.*))?$")
_REGISTRO_JUNTO = re.compile(r"^(?P<nome>.+?)\s+[—–-]\s+(?P<registro>(?:CAU|CREA)\b.+)$",
                             re.IGNORECASE)  # "Fulana - CAU A123" (autor e registro juntos)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.upper())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    sem_acento = re.sub(r"\((?:A|O|S|AS|OS|ES)\)", " ", sem_acento)  # "Proprietário(a)"
    sem_acento = re.sub(r"[.:º°ª]", " ", sem_acento).replace("/", " / ")
    return " ".join(sem_acento.split())


def _rotulo(linha: LinhaTexto) -> tuple[str | None, int] | None:
    """(campo, nº de palavras do rótulo) — ou None se a linha não é rótulo.

    Se o rótulo não ocupa a linha toda, o resto da linha é o valor ("Proprietário: João").
    """
    normalizado = _normalizar(linha.texto)
    if normalizado in _CAMPO_DO_ROTULO:
        return _CAMPO_DO_ROTULO[normalizado], len(linha.palavras)
    for i, palavra in enumerate(linha.palavras[:-1]):
        if palavra.texto.endswith(":"):
            prefixo = _normalizar(" ".join(p.texto for p in linha.palavras[:i + 1]))
            if prefixo in _CAMPO_DO_ROTULO:
                return _CAMPO_DO_ROTULO[prefixo], i + 1
            break
    return None


def _valor_associado(rotulo: LinhaTexto, linhas: list[LinhaTexto],
                     sao_rotulos: set[int]) -> tuple[LinhaTexto, str] | None:
    if rotulo.vertical:
        return None
    linhas = [ln for ln in linhas if not ln.vertical]  # direita/abaixo só no texto deitado
    altura = rotulo.altura
    direita = [ln for ln in linhas
               if abs(ln.centro_y - rotulo.centro_y) <= 0.6 * max(altura, ln.altura)
               and ln.bbox[0] > rotulo.bbox[2]
               and ln.bbox[0] - rotulo.bbox[2] <= DISTANCIA_DIREITA * altura]
    if direita:
        vizinha = min(direita, key=lambda ln: ln.bbox[0])
        if id(vizinha) not in sao_rotulos:
            return vizinha, "direita"
    abaixo = [ln for ln in linhas
              if ln.bbox[1] >= rotulo.bbox[3] - 0.2 * altura
              and ln.bbox[1] - rotulo.bbox[3] <= DISTANCIA_ABAIXO * altura
              and abs(ln.bbox[0] - rotulo.bbox[0]) <= 2 * altura]
    if abaixo:
        vizinha = min(abaixo, key=lambda ln: ln.bbox[1])
        if id(vizinha) not in sao_rotulos:
            return vizinha, "abaixo"
    return None


def _separar(campo: str, texto: str) -> list[tuple[str, str]]:
    """Campo composto → campos simples; tira o CPF de qualquer valor."""
    texto = _CPF.sub("", texto).strip(" —–-")
    if not texto:
        return []
    if campo == "LOTE_QUADRA":
        partes = [p.strip() for p in re.split(r"\s*/\s*|\s+[—–-]\s+", texto)]
        return list(zip(("LOTE", "QUADRA"), partes, strict=False)) if len(partes) == 2 else []
    if campo == "AUTOR" and (junto := _REGISTRO_JUNTO.match(texto)):
        return [("AUTOR", junto["nome"].strip()), ("AUTOR_REGISTRO", junto["registro"].strip())]
    if campo == "MATRICULA":
        m = _MATRICULA.match(texto)
        if not m:
            return []
        campos = [("MATRICULA", m.group(1))]
        if m.group(2) and re.search(r"[A-Za-zÀ-ú]", m.group(2)):
            campos.append(("CARTORIO", m.group(2).strip()))
        return campos
    return [(campo, texto)]


def _separar_dois_pontos(palavras: list[Palavra]) -> list[Palavra]:
    """ "Matrícula:nº" (OCR sem espaço depois dos dois-pontos) vira "Matrícula:" e "nº".

    A posição de cada parte é estimada pela proporção de letras dentro da palavra.
    """
    resultado = []
    for p in palavras:
        posicao = p.texto.find(":")
        if 0 < posicao < len(p.texto) - 1:
            x0, y0, x1, y1 = p.bbox
            corte = x0 + (x1 - x0) * (posicao + 1) / len(p.texto)
            resultado.append(p.model_copy(update={"texto": p.texto[:posicao + 1],
                                                  "bbox": (x0, y0, corte, y1)}))
            resultado.append(p.model_copy(update={"texto": p.texto[posicao + 1:],
                                                  "bbox": (corte, y0, x1, y1)}))
        else:
            resultado.append(p)
    return resultado


def ler_carimbo(pagina: PaginaLida, arquivo: str) -> list[ValorExtraido]:
    """Valores de identificação encontrados no carimbo (e em rótulos soltos) de uma página."""
    linhas = agrupar_linhas(_separar_dois_pontos(pagina.palavras))
    rotulos = {id(ln): r for ln in linhas if (r := _rotulo(ln)) is not None}
    valores: list[ValorExtraido] = []
    for linha in linhas:
        if id(linha) not in rotulos:
            continue
        campo, tamanho = rotulos[id(linha)]
        if campo is None:
            continue
        rotulo_texto = " ".join(p.texto for p in linha.palavras[:tamanho])
        if tamanho < len(linha.palavras):
            valor, como = LinhaTexto(linha.palavras[tamanho:]), "mesma linha"
        else:
            associado = _valor_associado(linha, linhas, set(rotulos))
            if associado is None:
                continue
            valor, como = associado
        ocr = any(p.origem == OrigemPalavra.OCR for p in valor.palavras)
        for campo_simples, texto in _separar(campo, valor.texto):
            evidencia = Evidencia(
                documento=arquivo, pagina=pagina.numero,
                trecho=f"{rotulo_texto} {texto}",
                bbox=uniao_bbox([linha.bbox, valor.bbox]),
                confianca_ocr=valor.confianca if ocr else None)
            valores.append(ValorExtraido(
                campo=campo_simples, valor=texto,
                origem=OrigemValor.OCR if ocr else OrigemValor.VETORIAL,
                confianca=round(CONFIANCA[como] * (valor.confianca if ocr else 1.0), 3),
                evidencias=[evidencia]))
    return valores
