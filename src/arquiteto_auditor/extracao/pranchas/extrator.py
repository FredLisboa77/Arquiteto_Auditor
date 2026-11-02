"""Junta as partes da extração das pranchas num só resultado: campo → valor com evidência.

Cada parte (carimbo, quadro de áreas, cotas...) devolve os valores que achou em cada folha.
O mesmo campo costuma aparecer em várias folhas (o carimbo se repete):
- todas concordam → um valor só, com a evidência de cada folha;
- discordam → fica o valor mais frequente, marcado "pendente de confirmação", com os outros
  valores na observação (o revisor decide; nunca se escolhe em silêncio — CLAUDE.md §3).
Campo que nenhuma parte achou fica fora do resultado: quem usa trata como "não encontrado".
"""

from __future__ import annotations

from collections import defaultdict

from arquiteto_auditor.dominio.documento import DocumentoLido
from arquiteto_auditor.dominio.modelos import StatusConfirmacao, TipoDocumento, ValorExtraido
from arquiteto_auditor.extracao.pranchas.carimbo import ler_carimbo
from arquiteto_auditor.extracao.pranchas.quadro import ler_quadro_areas

PENALIDADE_DIVERGENCIA = 0.6  # a confiança cai quando as folhas não concordam


def _chave(valor: float | str) -> str:
    return " ".join(str(valor).casefold().split())


def _consolidar(campo: str, achados: list[ValorExtraido]) -> ValorExtraido:
    grupos: dict[str, list[ValorExtraido]] = defaultdict(list)
    for achado in achados:
        grupos[_chave(achado.valor)].append(achado)
    ordem = sorted(grupos.values(), key=len, reverse=True)  # empate: o que apareceu antes
    escolhidos = ordem[0]
    evidencias = [e for a in escolhidos for e in a.evidencias]
    confianca = min(a.confianca for a in escolhidos)
    if len(ordem) == 1:
        return escolhidos[0].model_copy(update={"evidencias": evidencias,
                                                "confianca": confianca})
    outros = "; ".join(
        f"{grupo[0].valor} (pág. {', '.join(str(e.pagina) for a in grupo for e in a.evidencias)})"
        for grupo in ordem[1:])
    return escolhidos[0].model_copy(update={
        "evidencias": evidencias,
        "confianca": round(confianca * PENALIDADE_DIVERGENCIA, 3),
        "status": StatusConfirmacao.PENDENTE,
        "observacao": f"Valores diferentes entre as folhas: {outros}."})


def extrair_pranchas(documentos: list[DocumentoLido]) -> dict[str, ValorExtraido]:
    """Valores extraídos das pranchas do conjunto (os outros documentos são ignorados)."""
    achados: dict[str, list[ValorExtraido]] = defaultdict(list)
    for documento in documentos:
        if documento.tipo != TipoDocumento.PRANCHA:
            continue
        for pagina in documento.paginas:
            for leitor in (ler_carimbo, ler_quadro_areas):
                for valor in leitor(pagina, documento.arquivo):
                    achados[valor.campo].append(valor)
    return {campo: _consolidar(campo, lista) for campo, lista in achados.items()}
