"""Os parâmetros urbanísticos que a lei e a norma do condomínio podem definir.

Para cada parâmetro: as chaves do catálogo que ele alimenta (o recuo lateral vale para os
dois lados), o nome usado no pedido ao LLM, os sinônimos que o identificam no texto e nos
cabeçalhos de tabela, e as palavras que indicam uma regra de EXCEÇÃO que não é o parâmetro
do lote (muro perimetral, gradil, tapume, lote de esquina, beiral...).

Sinônimos e exceções são comparados em maiúsculas e sem acentos (texto_corrido.normalizar).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from arquiteto_auditor.extracao.texto_corrido import normalizar

JANELA_APOS_O_NUMERO = 70  # caracteres


@dataclass(frozen=True)
class DefinicaoParametro:
    nome: str  # identificador interno, ex.: "recuo_lateral"
    chaves: tuple[str, ...]  # chaves do catálogo (dominio/catalogo.toml)
    descricao: str  # como o parâmetro é pedido ao LLM
    limite: str  # "minimo" ou "maximo"
    unidade: str | None  # unidade interna: "m", "m2", "%", "pavimentos" ou None
    sinonimos: tuple[str, ...]
    excecoes: tuple[str, ...] = ()
    # Exceções que só valem logo depois do número ("muro de 80 cm no trecho do recuo
    # frontal"): na mesma frase pode estar a altura que vale ("... até a altura de 2,20 m").
    excecoes_apos_o_numero: tuple[str, ...] = ()
    # Parâmetro que as leis de uso do solo costumam definir. Achado só na norma do condomínio,
    # pode ser que a lei defina e a leitura dela tenha falhado (ex.: tabela escaneada).
    tipico_da_lei: bool = True

    def citado_em(self, texto: str) -> bool:
        return _contem(normalizar(texto), self.sinonimos)

    def citado_sem_espacos(self, texto: str) -> bool:
        """Para cabeçalhos de tabela, em que o texto pode quebrar no meio da palavra."""
        compacto = re.sub(r"\s", "", normalizar(texto))
        return any(re.sub(r"\s", "", s) in compacto for s in self.sinonimos)

    def tem_excecao(self, texto: str) -> bool:
        return _contem(normalizar(texto), self.excecoes)

    def tem_excecao_apos_o_numero(self, texto_depois: str) -> bool:
        return _contem(normalizar(texto_depois[:JANELA_APOS_O_NUMERO]),
                       self.excecoes_apos_o_numero)


def _contem(normal: str, termos: tuple[str, ...]) -> bool:
    return any(re.search(r"(?<![A-Z])" + re.escape(t) + r"(?![A-Z])", normal) for t in termos)


_EXCECOES_DO_LOTE = ("ESQUINA", "BEIRA", "BEIRAIS", "MARQUISE", "BRISE", "EDICULA", "TAPUME",
                     "SUBSOLO", "NAO RESIDENCIA")
# Regras para prédios altos (ex.: "afastamentos para edificações com mais de 2 pavimentos").
_EXCECOES_GERAIS = _EXCECOES_DO_LOTE + ("MAIS DE 2 PAVIMENTOS",)

DEFINICOES = (
    DefinicaoParametro(
        "lote_area_min", ("LOTE_AREA_MIN",), "área mínima do lote (lote mínimo)", "minimo",
        "m2",
        ("LOTE MINIMO", "AREA MINIMA DO LOTE", "AREA MINIMA DE LOTE", "AREA MINIMA DOS LOTES"),
        _EXCECOES_GERAIS),
    DefinicaoParametro(
        "testada_min", ("LOTE_TESTADA_MIN",), "testada mínima do lote", "minimo", "m",
        ("TESTADA MINIMA", "FRENTE MINIMA"), _EXCECOES_GERAIS),
    DefinicaoParametro(
        "recuo_frontal", ("RECUO_FRONTAL",), "recuo frontal mínimo", "minimo", "m",
        ("RECUO FRONTAL", "AFASTAMENTO FRONTAL", "RECUO DE FRENTE", "RECUO MINIMO FRONTAL"),
        _EXCECOES_GERAIS),
    DefinicaoParametro(
        "recuo_lateral", ("RECUO_LATERAL_E", "RECUO_LATERAL_D"), "recuo lateral mínimo",
        "minimo", "m",
        ("RECUO LATERAL", "RECUOS LATERAIS", "AFASTAMENTO LATERAL", "AFASTAMENTOS LATERAIS"),
        _EXCECOES_GERAIS),
    DefinicaoParametro(
        "recuo_fundos", ("RECUO_FUNDOS",), "recuo de fundos mínimo", "minimo", "m",
        ("RECUO DE FUNDOS", "RECUO DE FUNDO", "RECUO DO FUNDO", "RECUO DOS FUNDOS",
         "AFASTAMENTO DE FUNDOS", "AFASTAMENTO DE FUNDO"), _EXCECOES_GERAIS),
    DefinicaoParametro(
        "to_max", ("TO_MAX",), "taxa de ocupação máxima", "maximo", "%",
        ("TAXA DE OCUPACAO", "INDICE DE OCUPACAO", "T.O."), _EXCECOES_GERAIS),
    DefinicaoParametro(
        "ca_max", ("CA_MAX",), "coeficiente de aproveitamento máximo", "maximo", None,
        ("COEFICIENTE DE APROVEITAMENTO", "INDICE DE APROVEITAMENTO", "C.A."),
        _EXCECOES_GERAIS),
    DefinicaoParametro(
        "permeavel_min", ("PERMEAVEL_MIN",), "taxa de permeabilidade mínima", "minimo", "%",
        ("PERMEABILIDADE", "AREA PERMEAVEL", "TAXA PERMEAVEL"), _EXCECOES_GERAIS),
    DefinicaoParametro(
        "altura_max", ("ALTURA_MAX",), "altura máxima da edificação", "maximo", "m",
        ("ALTURA MAXIMA", "ALTURA DA EDIFICACAO", "ALTURA TOTAL DA EDIFICACAO", "GABARITO"),
        _EXCECOES_GERAIS + ("MURO", "MUROS", "GRADIL", "CERCA", "PLATIBANDA", "CAIXA D")),
    DefinicaoParametro(
        "pavimentos_max", ("PAVIMENTOS_MAX",), "número máximo de pavimentos", "maximo",
        "pavimentos", ("PAVIMENTOS", "PAVIMENTO"), _EXCECOES_DO_LOTE),
    DefinicaoParametro(
        "muro_altura_max", ("MURO_ALTURA_MAX",),
        "altura máxima permitida para os muros de divisa entre lotes (fundos e laterais); "
        "se houver alturas diferentes por trecho, a maior altura permitida", "maximo", "m",
        ("MURO", "MUROS"),
        ("PERIMETRAL", "GRADIL", "CERCA VIVA", "TAPUME", "ARRIMO", "NAO PODERA SER CONSTRUIDO",
         "PROIBIDA A CONSTRUCAO"),
        # Muro rebaixado na faixa do recuo frontal é exceção, não a altura máxima do muro.
        excecoes_apos_o_numero=("RECUO FRONTAL", "FAIXA DO RECUO", "TRECHO DO RECUO"),
        tipico_da_lei=False),
    DefinicaoParametro(
        "area_construida_min", ("AREA_CONSTR_MIN",), "área construída mínima da residência",
        "minimo", "m2", ("AREA CONSTRUIDA", "AREA DE CONSTRUCAO", "AREA MINIMA CONSTRUIDA"),
        _EXCECOES_GERAIS + ("SUPERIOR A", "ACIMA DE"), tipico_da_lei=False),
)

POR_CHAVE = {chave: definicao for definicao in DEFINICOES for chave in definicao.chaves}
