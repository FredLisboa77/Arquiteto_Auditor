"""Gabarito: a resposta certa de um conjunto de documentos de teste.

Cada conjunto sintético (e o conjunto real, só na sua máquina) tem um gabarito.json com os
itens que o software deveria apontar. A avaliação (Fase 13) compara o resultado com ele.
Formato documentado em docs/esquemas/ (esquema + exemplo).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from arquiteto_auditor.dominio.catalogo import DefinicaoVerificacao, carregar_catalogo
from arquiteto_auditor.dominio.modelos import ResultadoComparacao, StatusItem

FonteDocumento = Literal[
    "prancha", "memorial", "matricula", "escritura", "consulta_previa", "lei_municipal",
    "norma_condominio",
]
# Em valores_esperados também se pode informar o valor de cada fonte de parâmetro.
FonteValor = Literal[
    "prancha", "memorial", "matricula", "escritura", "consulta_previa", "lei_municipal",
    "norma_condominio", "prefeitura", "condominio", "adotado", "calculado",
]


class GabaritoInvalido(Exception):
    pass


@cache
def _catalogo() -> dict[str, DefinicaoVerificacao]:
    return carregar_catalogo()


def _checar_chave(chave: str) -> str:
    if chave not in _catalogo():
        raise ValueError(f"chave {chave!r} não existe no catálogo de verificações")
    return chave


def _checar_escopo(chave: str, escopo: str | None) -> None:
    definicao = _catalogo().get(chave)
    if definicao is None:
        return
    if definicao.escopo and not escopo and not definicao.escopo_opcional:
        raise ValueError(
            f"a chave {chave} exige 'escopo' (ex.: \"{definicao.escopo}=1\")"
        )
    if not definicao.escopo and escopo:
        raise ValueError(f"a chave {chave} não usa 'escopo'; remova-o")


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ItemEsperado(_Modelo):
    chave: str
    escopo: str | None = None
    status: StatusItem
    descricao: str | None = None  # explicação do erro injetado, para quem lê o gabarito
    documentos: list[FonteDocumento] = Field(default_factory=list)
    valor_projeto: float | str | None = None
    limite: float | None = None

    _chave_valida = field_validator("chave")(_checar_chave)

    @model_validator(mode="after")
    def _escopo_coerente(self):
        _checar_escopo(self.chave, self.escopo)
        return self


class ComparacaoEsperada(_Modelo):
    chave: str
    escopo: str | None = None
    resultado: ResultadoComparacao

    _chave_valida = field_validator("chave")(_checar_chave)

    @model_validator(mode="after")
    def _escopo_coerente(self):
        _checar_escopo(self.chave, self.escopo)
        return self


class Gabarito(_Modelo):
    # Caminho do esquema, para o VS Code autocompletar e validar enquanto você digita.
    esquema: str | None = Field(default=None, alias="$schema")
    conjunto: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    versao_gabarito: int = Field(ge=1)
    rodada: str = Field(pattern=r"^R\d{2}$")
    conjunto_anterior: str | None = None  # conjunto da rodada anterior (para R01, R02...)
    reservado_avaliacao: bool = False  # não usar no desenvolvimento das regras
    descricao: str | None = None
    zona: str | None = None
    valores_esperados: dict[str, dict[FonteValor, float | str]] = Field(default_factory=dict)
    itens_esperados: list[ItemEsperado] = Field(min_length=1)
    comparacao_rodada_anterior: list[ComparacaoEsperada] = Field(default_factory=list)

    @field_validator("valores_esperados")
    @classmethod
    def _chaves_de_valores(cls, valores):
        for chave in valores:
            _checar_chave(chave)
        return valores

    @model_validator(mode="after")
    def _coerencia(self):
        vistos = set()
        for item in self.itens_esperados:
            identificacao = (item.chave, item.escopo)
            if identificacao in vistos:
                escopo = f" ({item.escopo})" if item.escopo else ""
                raise ValueError(f"item duplicado em itens_esperados: {item.chave}{escopo}")
            vistos.add(identificacao)
        if self.comparacao_rodada_anterior:
            if self.rodada == "R00":
                raise ValueError(
                    "a rodada R00 não tem rodada anterior; remova comparacao_rodada_anterior"
                )
            if not self.conjunto_anterior:
                raise ValueError("comparacao_rodada_anterior exige 'conjunto_anterior'")
        return self

    def erros_esperados(self) -> list[ItemEsperado]:
        """Itens que representam problemas reais (base para medir a revocação)."""
        return [
            i for i in self.itens_esperados
            if i.status in (StatusItem.NAO_ATENDE, StatusItem.DIVERGENTE)
        ]


# ---------------------------------------------------------------- carregar e explicar erros


def _local(loc: tuple) -> str:
    texto = ""
    for parte in loc:
        if parte == "[key]":
            continue
        if isinstance(parte, int):
            texto += f"[{parte}]"
        else:
            texto += f".{parte}" if texto else str(parte)
    return texto or "gabarito"


_EXEMPLOS_DE_FORMATO = {
    r"^R\d{2}$": "R seguido de dois dígitos, ex.: R00, R01",
    r"^[a-z0-9][a-z0-9-]*$": "letras minúsculas, números e hífen, ex.: sint-001",
}


def _traduzir(erro: dict) -> str:
    tipo, ctx, entrada = erro["type"], erro.get("ctx", {}), erro.get("input")
    if tipo == "missing":
        motivo = "campo obrigatório ausente"
    elif tipo == "extra_forbidden":
        motivo = "campo desconhecido"
    elif tipo in ("enum", "literal_error"):
        permitidos = str(ctx.get("expected", "")).replace(" or ", " ou ")
        motivo = f"valor {entrada!r} não permitido; use um de: {permitidos}"
    elif tipo == "string_pattern_mismatch":
        exemplo = _EXEMPLOS_DE_FORMATO.get(ctx.get("pattern"), ctx.get("pattern"))
        motivo = f"formato inválido {entrada!r} (esperado: {exemplo})"
    elif tipo == "greater_than_equal":
        motivo = f"deve ser maior ou igual a {ctx.get('ge')} (recebido: {entrada!r})"
    elif tipo == "too_short":
        motivo = "não pode ficar vazio"
    elif tipo in ("int_parsing", "int_type", "float_parsing", "float_type", "int_from_float"):
        motivo = f"deve ser um número (recebido: {entrada!r})"
    elif tipo == "string_type":
        motivo = f"deve ser um texto (recebido: {entrada!r})"
    elif tipo == "value_error":
        motivo = str(ctx.get("error", erro["msg"]))
    else:
        motivo = erro["msg"]
    return f"{_local(erro['loc'])}: {motivo}"


def carregar_gabarito(caminho: Path) -> Gabarito:
    nome = Path(caminho).name
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise GabaritoInvalido(
            f"{nome}: JSON inválido na linha {erro.lineno}, coluna {erro.colno} ({erro.msg})"
        ) from erro
    try:
        return Gabarito.model_validate(dados)
    except ValidationError as erro:
        linhas = "\n".join(f"  - {_traduzir(e)}" for e in erro.errors())
        raise GabaritoInvalido(f"{nome}: gabarito inválido\n{linhas}") from erro


def esquema_json() -> dict:
    """Esquema JSON do gabarito (editores como o VS Code usam para autocompletar)."""
    return Gabarito.model_json_schema()
