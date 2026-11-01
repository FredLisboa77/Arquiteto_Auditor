"""Classificação do tipo de documento por pistas de texto e de formato (sem LLM).

Cada tipo tem pistas típicas de documentos brasileiros (expressões fixas de cartório, de leis,
de memoriais...), com pesos. Ganha o tipo com mais pontos; a confiança cai quando o segundo
colocado chega perto. Pranchas também são reconhecidas pelo formato (folha grande e muito
desenho), porque podem não ter texto selecionável nenhum (texto SHX, perspectivas).
O revisor pode corrigir o tipo na interface (docs/02-mvp.md §2.2).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from arquiteto_auditor.dominio.documento import DocumentoLido
from arquiteto_auditor.dominio.modelos import TipoDocumento

# (expressão regular sobre o texto em maiúsculas e sem acentos, peso)
PISTAS: dict[TipoDocumento, list[tuple[str, float]]] = {
    TipoDocumento.PRANCHA: [
        (r"\bQUADRO DE AREAS\b", 3), (r"\bPLANTA (DE SITUACAO|DE LOCALIZACAO|BAIXA)\b", 3),
        (r"\bESCALA\b", 1), (r"\bCORTE\b", 1), (r"\bFACHADA\b", 1), (r"\bPRANCHA\b", 1),
        (r"\b1:\d{2,3}\b", 1), (r"\bRESP(ONSAVEL)?\.? TECNICO\b|\bAUTOR DO PROJETO\b", 1),
    ],
    TipoDocumento.MATRICULA: [
        (r"\bREGISTRO DE IMOVEIS\b", 2), (r"\bLIVRO N. ?2\b|\bREGISTRO GERAL\b", 3),
        (r"\bCERTIDAO DE INTEIRO TEOR\b", 4), (r"\bMATRICULA N", 2),
        (r"\b(R|AV)-\d+/[\d.]+", 2), (r"\bO OFICIAL\b", 1),
    ],
    TipoDocumento.ESCRITURA: [
        (r"\bESCRITURA PUBLICA\b", 4), (r"\bOUTORGANTES?\b", 3), (r"\bOUTORGADOS?\b", 3),
        (r"\bTABELI(AO|ONATO)\b", 2), (r"\bSAIBAM\b", 3), (r"\bLAVRAD[AO]\b", 1),
    ],
    TipoDocumento.MEMORIAL: [
        (r"\bMEMORIAL DESCRITIVO\b", 6), (r"\bESPECIFICAC(AO|OES) TECNICAS?\b", 2),
        (r"\bTRATA-SE DE UMA EDIFICACAO\b", 2), (r"\bAMBIENTES\b", 1),
    ],
    TipoDocumento.LEI_MUNICIPAL: [
        (r"\bLEI (COMPLEMENTAR )?N", 3), (r"\bART\. ?\d+", 1), (r"\bPREFEITO\b", 2),
        (r"\bCAMARA MUNICIPAL\b", 2), (r"\bZONEAMENTO\b", 1), (r"\bCODIGO DE OBRAS\b", 3),
        (r"\bANEXO [IVX]+\b", 1), (r"\bDISPOE SOBRE\b", 2),
    ],
    TipoDocumento.NORMA_CONDOMINIO: [
        (r"\bREGULAMENTO\b", 2), (r"\bCONVENCAO DO CONDOMINIO\b", 3), (r"\bSINDIC[OA]\b", 2),
        (r"\bCOMISSAO DE OBRAS\b", 3), (r"\bCONDOMINOS?\b", 2),
        (r"\bNORMAS (DE OCUPACAO|CONSTRUTIVAS|DE CONSTRUCAO)\b", 3),
        (r"\bASSEMBLEIA\b", 1),
    ],
}
LIMITE_OCORRENCIAS = 5  # uma pista repetida muitas vezes não domina sozinha
FOLHA_GRANDE_PT = 1100  # maior lado acima disso (≈ 388 mm) = formato de prancha (A3 ou maior)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.upper())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.split())  # quebras de linha não separam expressões


@dataclass(frozen=True)
class Classificacao:
    tipo: TipoDocumento
    confianca: float
    motivo: str


def classificar(documento: DocumentoLido, paginas: int = 4) -> Classificacao:
    """Tipo do documento a partir das primeiras páginas (texto, formato e desenho)."""
    texto = _normalizar("\n".join(p.texto for p in documento.paginas[:paginas]))
    pontos: dict[TipoDocumento, float] = {}
    achados: dict[TipoDocumento, list[str]] = {}
    for tipo, pistas in PISTAS.items():
        for padrao, peso in pistas:
            ocorrencias = len(re.findall(padrao, texto))
            if ocorrencias:
                pontos[tipo] = pontos.get(tipo, 0.0) + peso * min(ocorrencias, LIMITE_OCORRENCIAS)
                achados.setdefault(tipo, []).append(padrao)

    primeira = documento.paginas[0] if documento.paginas else None
    if primeira and max(primeira.largura, primeira.altura) > FOLHA_GRANDE_PT:
        desenhos = max(p.desenhos for p in documento.paginas)
        pontos[TipoDocumento.PRANCHA] = pontos.get(TipoDocumento.PRANCHA, 0.0) + (
            12 if desenhos > 50 else 4)
        achados.setdefault(TipoDocumento.PRANCHA, []).append("folha de formato grande")

    if not pontos:
        return Classificacao(TipoDocumento.OUTRO, 0.0, "nenhuma pista reconhecida")
    ordem = sorted(pontos.items(), key=lambda item: item[1], reverse=True)
    vencedor, melhor = ordem[0]
    segundo = ordem[1][1] if len(ordem) > 1 else 0.0
    confianca = round(min(1.0, melhor / 10) * (1 - segundo / (melhor + segundo)) * 2, 2)
    motivo = f"pistas de {vencedor.value}: {len(achados[vencedor])}"
    return Classificacao(vencedor, min(confianca, 1.0), motivo)
