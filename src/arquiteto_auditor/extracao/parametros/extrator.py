"""Parâmetros de UM documento: a lei municipal (prefeitura) ou a norma do condomínio.

Lei: precisa da zona do lote. Se o revisor não informou, ela é procurada pelo nome do
condomínio (zona.py); sem zona, nenhum parâmetro é lido (nunca se presume a zona).
Valores das tabelas (código) e do texto (LLM) de cada parâmetro são juntados por
consolidar: concordam → automático; discordam → pendente, com as opções na observação.

Sem o Ollama (modo degradado, docs/03 §6.4) as tabelas continuam sendo lidas; o que só está
em texto corrido fica "não encontrado" e o resultado avisa que o LLM não foi usado.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from arquiteto_auditor.dominio.documento import DocumentoLido
from arquiteto_auditor.dominio.modelos import ValorExtraido
from arquiteto_auditor.extracao.consolidar import consolidar
from arquiteto_auditor.extracao.parametros.definicoes import DEFINICOES
from arquiteto_auditor.extracao.parametros.tabelas import ler_tabelas_de_parametros
from arquiteto_auditor.extracao.parametros.texto import ler_texto_de_parametros
from arquiteto_auditor.extracao.parametros.trechos import recortar
from arquiteto_auditor.extracao.parametros.zona import identificar_zona
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido
from arquiteto_auditor.ingestao.tabelas import ler_tabelas
from arquiteto_auditor.llm.cliente import ClienteLLM, LLMIndisponivel


@dataclass
class ParametrosDoDocumento:
    arquivo: str
    fonte: Literal["prefeitura", "condominio"]
    zona: ValorExtraido | None = None  # só na lei
    valores: dict[str, ValorExtraido] = field(default_factory=dict)  # por chave do catálogo
    sem_llm: bool = False  # o texto corrido não foi lido (Ollama indisponível)


def ler_parametros(caminho: Path, documento: DocumentoLido,
                   fonte: Literal["prefeitura", "condominio"], *,
                   cliente: ClienteLLM | None, nome_condominio: str | None = None,
                   zona_informada: str | None = None,
                   area_lote: float | None = None) -> ParametrosDoDocumento:
    """Parâmetros do documento (ver o início do módulo). cliente=None → sem LLM."""
    corrido = TextoCorrido(documento)
    tabelas = ler_tabelas(Path(caminho), documento)
    trechos = recortar(corrido, tabelas)
    resultado = ParametrosDoDocumento(arquivo=documento.arquivo, fonte=fonte)

    zona = None
    if fonte == "prefeitura":
        if zona_informada:
            zona = zona_informada
        else:
            resultado.zona = identificar_zona(trechos, corrido, nome_condominio,
                                              documento.arquivo)
            zona = resultado.zona.valor if resultado.zona else None
        if zona is None:
            return resultado  # a interface pergunta a zona ao revisor

    achados: dict[str, list[ValorExtraido]] = defaultdict(list)
    if zona is not None:
        for chave, valores in ler_tabelas_de_parametros(tabelas, str(zona), documento.arquivo,
                                                        area_lote).items():
            achados[chave] += valores
    if cliente is None:
        resultado.sem_llm = True
    else:
        try:
            lidos = ler_texto_de_parametros(trechos, corrido, documento.arquivo, DEFINICOES,
                                            str(zona) if zona else None, cliente)
        except LLMIndisponivel:
            resultado.sem_llm = True
        else:
            for chave, valores in lidos.items():
                achados[chave] += valores

    resultado.valores = {chave: consolidar(valores) for chave, valores in achados.items()}
    return resultado
