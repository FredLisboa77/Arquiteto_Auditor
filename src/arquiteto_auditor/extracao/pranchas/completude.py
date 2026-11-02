"""Completude das pranchas: o que deveria estar escrito e não está (docs/02 §4.1).

8 dos 11 erros do conjunto real eram de OMISSÃO, não de valor. Aqui se constata, sem LLM:
- COTA_INDEFINIDA (por elemento): a linha de cota está desenhada, mas sem o número (cota "só
  gráfica"). As linhas de cota vêm da ingestão (PaginaLida.cotas_desenhadas). O elemento de
  cada linha sai da forma do desenho:
    · na situação, a cadeia de três cotas emendadas com o total paralelo, orientada pela rua
      (mesma regra de cotas.py: frente do lado da rua, esquerda de quem olha da rua);
    · no corte, a linha de cota vertical mais longa é a altura total;
    · o muro é a linha de cota vertical mais próxima do texto "MURO".
  Linha que não se consegue associar a um elemento não gera constatação (não se afirma).
- NORTE_INDICADO: um "N" (ou "NORTE") isolado em alguma folha.
- ID_PROPRIETARIO: o carimbo traz o nome do proprietário.
- ASSINATURA_AUTOR / ASSINATURA_PROPRIETARIO: assinatura digital no PDF cujo titular tem o
  nome do autor (ou do proprietário) lido no carimbo. Sem o nome do proprietário, qualquer
  assinatura que não seja a do autor conta. Precisa estar em todos os arquivos de pranchas.
- ASSINATURA_DIGITAL_VALIDA: "alterada" se alguma assinatura não confere com o conteúdo, ou se
  algo foi salvo no arquivo depois de todas as assinaturas (ingestao/assinaturas.py).
"""

from __future__ import annotations

import re
import unicodedata

from arquiteto_auditor.dominio.constatacao import Constatacao, Situacao
from arquiteto_auditor.dominio.documento import DocumentoLido, PaginaLida
from arquiteto_auditor.dominio.modelos import Evidencia, TipoDocumento
from arquiteto_auditor.dominio.numeros import encontrar_valores
from arquiteto_auditor.extracao.pranchas.cotas import elementos_da_cadeia, rua_mais_proxima
from arquiteto_auditor.extracao.pranchas.linhas import LinhaTexto, agrupar_linhas, uniao_bbox

ENCAIXE = 1.5  # pt: pontas de cotas emendadas
DISTANCIA_TEXTO = 3  # em alturas de letra: até onde o número pertence à linha de cota
DISTANCIA_MURO = 10  # em alturas de letra: até onde a cota é a do muro
TRECHO_SEM_NUMERO = "[linha de cota sem número]"  # descrição (não há texto a citar)

Segmento = tuple[float, float, float, float]


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.upper())
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).strip(" .:")


def _vertical(s: Segmento) -> bool:
    return abs(s[2] - s[0]) < 0.5


def _textos_das_cotas(pagina: PaginaLida, linhas: list[LinhaTexto]) -> dict[Segmento, LinhaTexto]:
    """Cada texto com número vai para a linha de cota mais próxima (mesma orientação)."""
    resultado: dict[Segmento, tuple[float, LinhaTexto]] = {}
    for linha in linhas:
        if not encontrar_valores(linha.texto):
            continue
        x0, y0, x1, y1 = linha.bbox
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        melhor = None
        for s in pagina.cotas_desenhadas:
            if _vertical(s) != linha.vertical:
                continue
            ao_longo, de_lado, inicio, fim = (cy, abs(cx - s[0]), s[1], s[3]) if _vertical(s) \
                else (cx, abs(cy - s[1]), s[0], s[2])
            if inicio <= ao_longo <= fim and de_lado <= DISTANCIA_TEXTO * linha.altura and (
                    melhor is None or de_lado < melhor[0]):
                melhor = (de_lado, s)
        if melhor and (melhor[1] not in resultado or melhor[0] < resultado[melhor[1]][0]):
            resultado[melhor[1]] = (melhor[0], linha)
    return {s: linha for s, (_, linha) in resultado.items()}


def _cadeias(cotas: list[Segmento]) -> list[tuple[bool, list[Segmento], Segmento]]:
    """(vertical, três partes emendadas em ordem na folha, total paralelo)."""
    achadas = []
    for vertical in (False, True):
        mesmas = [s for s in cotas if _vertical(s) == vertical]
        eixo = 0 if vertical else 1  # coordenada fixa da linha (x da vertical, y da horizontal)
        inicio, fim = (1, 3) if vertical else (0, 2)
        for primeira in mesmas:
            partes = [primeira]
            while len(partes) < 4:
                seguinte = [s for s in mesmas if abs(s[eixo] - partes[-1][eixo]) < 0.5
                            and abs(s[inicio] - partes[-1][fim]) <= ENCAIXE]
                if not seguinte:
                    break
                partes.append(seguinte[0])
            anteriores = [s for s in mesmas if abs(s[eixo] - primeira[eixo]) < 0.5
                          and abs(s[fim] - primeira[inicio]) <= ENCAIXE]
            if len(partes) != 3 or anteriores:
                continue  # só cadeias de exatamente três partes, a partir da primeira
            for total in mesmas:
                if (total not in partes and 0 < abs(total[eixo] - primeira[eixo]) <= 60
                        and abs(total[inicio] - partes[0][inicio]) <= ENCAIXE
                        and abs(total[fim] - partes[-1][fim]) <= ENCAIXE):
                    achadas.append((vertical, partes, total))
                    break
    return achadas


def _constatar(elemento: str, segmento: Segmento, texto: LinhaTexto | None,
               pagina: PaginaLida, arquivo: str) -> Constatacao:
    if texto is not None:
        return Constatacao("COTA_INDEFINIDA", Situacao.PRESENTE, f"elemento={elemento}",
                           (Evidencia(documento=arquivo, pagina=pagina.numero,
                                      trecho=texto.texto, bbox=texto.bbox),),
                           "cota escrita")
    return Constatacao("COTA_INDEFINIDA", Situacao.AUSENTE, f"elemento={elemento}",
                       (Evidencia(documento=arquivo, pagina=pagina.numero,
                                  trecho=TRECHO_SEM_NUMERO, bbox=segmento),),
                       "linha de cota desenhada sem o número (cota só gráfica)")


def _cotas_da_pagina(pagina: PaginaLida, arquivo: str) -> list[Constatacao]:
    linhas = agrupar_linhas(pagina.palavras)
    textos = _textos_das_cotas(pagina, linhas)
    constatacoes = []

    cadeias = _cadeias(pagina.cotas_desenhadas)
    if cadeias:
        regiao = uniao_bbox([s for _, partes, total in cadeias for s in (*partes, total)])
        rua = rua_mais_proxima(linhas, regiao)
        for vertical, partes, total in (cadeias if rua else []):
            meio = partes[1]
            centro = (meio[1] + meio[3]) / 2 if vertical else meio[1]
            elementos = elementos_da_cadeia(vertical, rua.centro_y > centro)
            for elemento, s in zip(elementos, (partes[0], partes[2], total), strict=True):
                constatacoes.append(_constatar(elemento, s, textos.get(s), pagina, arquivo))

    verticais = [s for s in pagina.cotas_desenhadas if _vertical(s)]
    if verticais and any(re.search(r"\bCORTE\b", _normalizar(ln.texto)) for ln in linhas):
        maior = max(verticais, key=lambda s: s[3] - s[1])
        constatacoes.append(_constatar("altura_total", maior, textos.get(maior), pagina,
                                       arquivo))
    for rotulo in linhas:
        if rotulo.vertical or _normalizar(rotulo.texto) != "MURO":
            continue
        perto = [s for s in verticais if _distancia(s, rotulo.bbox)
                 <= DISTANCIA_MURO * rotulo.altura]
        if perto:
            muro = min(perto, key=lambda s: _distancia(s, rotulo.bbox))
            constatacoes.append(_constatar("muro", muro, textos.get(muro), pagina, arquivo))
    return constatacoes


def _distancia(s: Segmento, caixa) -> float:
    dx = max(caixa[0] - s[2], s[0] - caixa[2], 0)
    dy = max(caixa[1] - s[3], s[1] - caixa[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def _consolidar_cotas(constatacoes: list[Constatacao]) -> list[Constatacao]:
    """O mesmo elemento em várias folhas: basta a cota escrita em uma delas."""
    por_escopo: dict[str, Constatacao] = {}
    for c in constatacoes:
        atual = por_escopo.get(c.escopo)
        if atual is None or (atual.situacao == Situacao.AUSENTE
                             and c.situacao == Situacao.PRESENTE):
            por_escopo[c.escopo] = c
    return list(por_escopo.values())


def _tokens(nome) -> set[str]:
    texto = str(getattr(nome, "valor", nome))  # aceita ValorExtraido ou texto
    return set(_normalizar(texto).split())


def _mesmo_nome(titular: str | None, nome) -> bool:
    """Um nome contém o outro (o certificado costuma trazer o nome completo)."""
    a, b = _tokens(titular or ""), _tokens(nome)
    return bool(a and b) and (a <= b or b <= a)


def _evidencia_assinatura(documento: DocumentoLido, assinatura) -> Evidencia:
    return Evidencia(documento=documento.arquivo, pagina=1,
                     trecho=f"[assinatura digital {assinatura.campo or ''} de "
                            f"{assinatura.titular or 'titular desconhecido'}]")


def _assinaturas(pranchas: list[DocumentoLido], valores: dict) -> list[Constatacao]:
    autor, proprietario = valores.get("AUTOR"), valores.get("PROPRIETARIO")
    resultado = []

    def de_quem(documento: DocumentoLido, chave: str):
        if chave == "ASSINATURA_AUTOR":
            return [a for a in documento.assinaturas if _mesmo_nome(a.titular, autor)]
        if proprietario is not None:
            return [a for a in documento.assinaturas if _mesmo_nome(a.titular, proprietario)]
        return [a for a in documento.assinaturas if not _mesmo_nome(a.titular, autor)]

    for chave, nome in (("ASSINATURA_AUTOR", autor), ("ASSINATURA_PROPRIETARIO", True)):
        if nome is None:
            continue  # sem o nome do autor não dá para saber de quem é cada assinatura
        faltando = [d.arquivo for d in pranchas if not de_quem(d, chave)]
        if faltando:
            resultado.append(Constatacao(chave, Situacao.AUSENTE,
                                         motivo=f"sem assinatura digital em {', '.join(faltando)}"))
        else:
            resultado.append(Constatacao(chave, Situacao.PRESENTE, evidencias=tuple(
                _evidencia_assinatura(d, a) for d in pranchas for a in de_quem(d, chave))))

    assinadas = [d for d in pranchas if d.assinaturas]
    violadas = [(d, a) for d in assinadas for a in d.assinaturas if not a.integra]
    descobertas = [d for d in assinadas if not any(a.cobre_arquivo_inteiro
                                                    for a in d.assinaturas)]
    if violadas:
        resultado.append(Constatacao(
            "ASSINATURA_DIGITAL_VALIDA", Situacao.ALTERADA,
            evidencias=tuple(_evidencia_assinatura(d, a) for d, a in violadas),
            motivo="o conteúdo não confere com a assinatura (alterado depois de assinado)"))
    elif descobertas:
        resultado.append(Constatacao(
            "ASSINATURA_DIGITAL_VALIDA", Situacao.ALTERADA,
            evidencias=tuple(_evidencia_assinatura(d, d.assinaturas[-1]) for d in descobertas),
            motivo="há alterações salvas no arquivo depois das assinaturas"))
    elif assinadas:
        resultado.append(Constatacao(
            "ASSINATURA_DIGITAL_VALIDA", Situacao.PRESENTE,
            evidencias=tuple(_evidencia_assinatura(d, a) for d in assinadas
                             for a in d.assinaturas),
            motivo="assinaturas íntegras (cadeia de confiança não verificada offline)"))
    return resultado


def verificar_completude(documentos: list[DocumentoLido], valores: dict) -> list[Constatacao]:
    """Constatações de completude das pranchas; `valores` = campos já extraídos."""
    pranchas = [d for d in documentos if d.tipo == TipoDocumento.PRANCHA]
    cotas: list[Constatacao] = []
    norte: Constatacao | None = None
    for documento in pranchas:
        for pagina in documento.paginas:
            cotas += _cotas_da_pagina(pagina, documento.arquivo)
            for linha in agrupar_linhas(pagina.palavras):
                if norte is None and _normalizar(linha.texto) in ("N", "NORTE"):
                    norte = Constatacao("NORTE_INDICADO", Situacao.PRESENTE, evidencias=(
                        Evidencia(documento=documento.arquivo, pagina=pagina.numero,
                                  trecho=linha.texto, bbox=linha.bbox),),
                        motivo="indicação do Norte encontrada")

    resultado = _consolidar_cotas(cotas)
    resultado.append(norte or Constatacao("NORTE_INDICADO", Situacao.AUSENTE,
                                          motivo="nenhum \"N\" ou \"NORTE\" nas pranchas"))
    resultado += _assinaturas(pranchas, valores)
    if "PROPRIETARIO" in valores:
        resultado.append(Constatacao("ID_PROPRIETARIO", Situacao.PRESENTE,
                                     motivo="proprietário identificado no carimbo"))
    else:
        resultado.append(Constatacao("ID_PROPRIETARIO", Situacao.AUSENTE,
                                     motivo="nome do proprietário não encontrado no carimbo"))
    return resultado
