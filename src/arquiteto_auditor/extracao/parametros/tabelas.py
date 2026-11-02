"""Parâmetros lidos nas tabelas da lei, pelo código (sem LLM).

O valor fica no cruzamento da célula da ZONA com a célula do PARÂMETRO. Três arranjos:
1. uma linha por zona, um parâmetro por coluna (cabeçalho em cima);
2. uma coluna por zona, um parâmetro por linha ("tabela invertida");
3. a zona numa célula mesclada que abrange várias linhas, um parâmetro por linha e uma
   coluna por CONDIÇÃO (ex.: "Lotes com área até 600 m²" × "acima de 600 m²").
No arranjo 3, a condição é escolhida pela área do lote; sem a área (ou se a condição não é
entendida), ficam todas as opções e o valor vai para a confirmação do revisor.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from arquiteto_auditor.dominio.modelos import Evidencia, OrigemValor, ValorExtraido
from arquiteto_auditor.dominio.numeros import encontrar_valores
from arquiteto_auditor.extracao.parametros.definicoes import DEFINICOES, DefinicaoParametro
from arquiteto_auditor.extracao.pranchas.linhas import uniao_bbox
from arquiteto_auditor.extracao.texto_corrido import normalizar
from arquiteto_auditor.ingestao.tabelas import Celula, Tabela

CONFIANCA_TABELA = 0.9


def mesma_zona(texto: str, zona: str) -> bool:
    """ "ZR-2" = "ZR 2" = "zr2"; "ZR-2" ≠ "ZR-20"."""
    def compacto(t):
        return re.sub(r"[\s\-–]", "", normalizar(t))
    return bool(texto.strip()) and compacto(texto) == compacto(zona)


@dataclass(frozen=True)
class _Achado:
    definicao: DefinicaoParametro
    valor: float
    celulas: tuple[Celula, ...]  # zona, parâmetro, (condição), valor
    pagina: int
    condicao: str | None = None


def _numero(celula: Celula | None) -> float | None:
    if celula is None:
        return None
    valores = encontrar_valores(celula.texto)
    if len(valores) != 1 or valores[0].ambiguo:
        return None
    return valores[0].valor


def _definicao_da_celula(celula: Celula) -> DefinicaoParametro | None:
    if not celula.texto or len(celula.texto) > 80 or _numero(celula) is not None:
        return None
    for definicao in DEFINICOES:
        if definicao.citado_sem_espacos(celula.texto) and not definicao.tem_excecao(
                celula.texto):
            return definicao
    return None


def _achados_da_tabela(tabela: Tabela, zona: str) -> list[_Achado]:
    zonas = [c for c in tabela.celulas if mesma_zona(c.texto, zona)]
    rotulos = [(c, d) for c in tabela.celulas if (d := _definicao_da_celula(c))]
    achados = []
    for z in zonas:
        for p, definicao in rotulos:
            if p.coluna == z.coluna:
                continue
            if p.ate_linha < z.linha:  # 1: parâmetro no cabeçalho, zona na linha
                for linha in range(z.linha, z.ate_linha + 1):
                    celula = tabela.celula(linha, p.coluna)
                    if (valor := _numero(celula)) is not None:
                        achados.append(_Achado(definicao, valor, (z, p, celula), tabela.pagina))
            elif z.ate_linha < p.linha:  # 2: zona no cabeçalho, parâmetro na linha
                celula = tabela.celula(p.linha, z.coluna)
                if (valor := _numero(celula)) is not None:
                    achados.append(_Achado(definicao, valor, (z, p, celula), tabela.pagina))
            elif z.linha <= p.linha <= z.ate_linha:  # 3: zona mesclada, colunas de condição
                for coluna in range(tabela.colunas):
                    if coluna in (z.coluna, p.coluna):
                        continue
                    celula = tabela.celula(p.linha, coluna)
                    if (valor := _numero(celula)) is None:
                        continue
                    cabecalho = tabela.celula(0, coluna)
                    condicao = cabecalho.texto if cabecalho and cabecalho is not celula else None
                    achados.append(_Achado(definicao, valor, (z, p, cabecalho, celula)
                                           if condicao else (z, p, celula), tabela.pagina,
                                           condicao))
    return achados


_ATE = re.compile(r"\b(ATE|INFERIOR A|MENOR QUE|MENORES QUE|IGUAL OU INFERIOR A)\b")
_ACIMA = re.compile(r"\b(ACIMA DE|SUPERIOR A|SUPERIORES A|MAIOR QUE|MAIORES QUE|MAIS DE)\b")


def condicao_atendida(condicao: str, area_lote: float) -> bool | None:
    """A condição de área ("até 600 m²", "acima de 600 m²") vale para o lote? None = não sei."""
    normal = normalizar(condicao)
    if not re.search(r"\bAREA\b", normal):
        return None
    valores = [v for v in encontrar_valores(condicao) if v.unidade in ("m2", None)]
    if len(valores) != 1:
        return None
    limite = valores[0].valor
    ate, acima = _ATE.search(normal), _ACIMA.search(normal)
    if ate and not acima:
        return area_lote <= limite
    if acima and not ate:
        return area_lote > limite
    return None


def _valor(achado: _Achado, chave: str, arquivo: str) -> ValorExtraido:
    celulas = [c for c in achado.celulas if c is not None]
    trecho = " | ".join(c.texto for c in celulas)
    evidencia = Evidencia(documento=arquivo, pagina=achado.pagina, trecho=trecho,
                          bbox=uniao_bbox(c.bbox for c in celulas))
    return ValorExtraido(campo=chave, valor=achado.valor, unidade=achado.definicao.unidade,
                         origem=OrigemValor.VETORIAL, confianca=CONFIANCA_TABELA,
                         evidencias=[evidencia],
                         observacao=f"Condição: {achado.condicao}." if achado.condicao
                         else None)


def ler_tabelas_de_parametros(tabelas: list[Tabela], zona: str, arquivo: str,
                              area_lote: float | None = None) -> dict[str, list[ValorExtraido]]:
    """Valores encontrados nas tabelas, por chave do catálogo (um ou mais por chave)."""
    por_definicao: dict[str, list[_Achado]] = defaultdict(list)
    for tabela in tabelas:
        for achado in _achados_da_tabela(tabela, zona):
            por_definicao[achado.definicao.nome].append(achado)

    resultado: dict[str, list[ValorExtraido]] = defaultdict(list)
    for achados in por_definicao.values():
        if area_lote is not None and any(a.condicao for a in achados):
            validos = [a for a in achados
                       if a.condicao is None or condicao_atendida(a.condicao, area_lote)]
            achados = validos or achados  # nada entendido: todas as opções, para o revisor
        for achado in achados:
            for chave in achado.definicao.chaves:
                resultado[chave].append(_valor(achado, chave, arquivo))
    return dict(resultado)
