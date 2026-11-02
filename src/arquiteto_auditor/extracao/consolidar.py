"""Junta vários achados do mesmo campo (várias folhas, várias partes do documento).

- todos concordam → um valor só, com a evidência de cada achado e a confiança (e o status)
  do achado mais confiável: uma cota com rótulo confirma a mesma cota achada pela cadeia;
- discordam → fica o valor mais frequente, "pendente de confirmação", com os outros valores
  na observação (o revisor decide; nunca se escolhe em silêncio — CLAUDE.md §3);
- valor lido por OCR com confiança abaixo do limite (config: ocr.limiar_confianca) também
  fica pendente: baixa confiança é visível (CLAUDE.md §3, princípio 5).
"""

from __future__ import annotations

from collections import defaultdict

from arquiteto_auditor.config import limiar_confianca_ocr
from arquiteto_auditor.dominio.modelos import StatusConfirmacao, ValorExtraido

PENALIDADE_DIVERGENCIA = 0.6  # a confiança cai quando as folhas não concordam


def _chave(valor: float | str) -> str:
    return " ".join(str(valor).casefold().split())


def consolidar(achados: list[ValorExtraido]) -> ValorExtraido:
    """Um valor a partir de vários achados do mesmo campo (ver o início do módulo)."""
    return _marcar_ocr_fraco(_juntar(achados))


def _marcar_ocr_fraco(valor: ValorExtraido) -> ValorExtraido:
    leituras = [e.confianca_ocr for e in valor.evidencias if e.confianca_ocr is not None]
    if not leituras or max(leituras) >= limiar_confianca_ocr():
        return valor  # pelo menos uma leitura boa do mesmo valor basta
    motivo = f"leitura (OCR) com baixa confiança ({max(leituras):.2f})"
    observacao = (f"{valor.observacao} Confirme: {motivo}." if valor.observacao
                  else f"Confirme: {motivo}.")
    return valor.model_copy(update={"status": StatusConfirmacao.PENDENTE,
                                    "observacao": observacao})


def _juntar(achados: list[ValorExtraido]) -> ValorExtraido:
    grupos: dict[str, list[ValorExtraido]] = defaultdict(list)
    for achado in achados:
        grupos[_chave(achado.valor)].append(achado)
    ordem = sorted(grupos.values(), key=len, reverse=True)  # empate: o que apareceu antes
    escolhidos = ordem[0]
    evidencias = [e for a in escolhidos for e in a.evidencias]
    base = max(escolhidos, key=lambda a: a.confianca)
    confianca = base.confianca
    if len(ordem) == 1:
        return base.model_copy(update={"evidencias": evidencias})
    outros = "; ".join(
        f"{grupo[0].valor} (pág. {', '.join(str(e.pagina) for a in grupo for e in a.evidencias)})"
        for grupo in ordem[1:])
    return base.model_copy(update={
        "evidencias": evidencias,
        "confianca": round(confianca * PENALIDADE_DIVERGENCIA, 3),
        "status": StatusConfirmacao.PENDENTE,
        "observacao": f"Valores diferentes entre as folhas: {outros}."})
