"""Carrega o catálogo de verificações (catalogo.toml) e garante que ele é coerente."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arquiteto_auditor.dominio.modelos import PADRAO_CHAVE

CATALOGO_PADRAO = Path(__file__).with_name("catalogo.toml")


class CatalogoInvalido(Exception):
    pass


class DefinicaoVerificacao(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chave: str = Field(pattern=PADRAO_CHAVE)
    nome: str = Field(min_length=1)
    tipo: Literal["identificacao", "consistencia", "parametro", "aritmetica", "completude"]
    descricao: str = Field(min_length=1)
    escopo: Literal["pavimento", "elemento"] | None = None


def carregar_catalogo(arquivo: Path = CATALOGO_PADRAO) -> dict[str, DefinicaoVerificacao]:
    dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    catalogo: dict[str, DefinicaoVerificacao] = {}
    for posicao, entrada in enumerate(dados.get("verificacao", []), start=1):
        try:
            definicao = DefinicaoVerificacao(**entrada)
        except ValidationError as erro:
            raise CatalogoInvalido(
                f"{arquivo.name}, verificação nº {posicao} ({entrada.get('chave')!r}): {erro}"
            ) from erro
        if definicao.chave in catalogo:
            raise CatalogoInvalido(f"{arquivo.name}: chave duplicada {definicao.chave!r}")
        catalogo[definicao.chave] = definicao
    return catalogo
