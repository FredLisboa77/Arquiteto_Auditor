"""Matrícula do imóvel: atos (R-n, AV-n) e estado atual, como lidos dos documentos (Fase 7).

O estado atual sai da aplicação dos atos em ordem (docs/03 §5.3): a área vem da abertura e
muda a cada retificação; o proprietário muda a cada transmissão; ônus entram e saem
(cancelamento). Cada campo do estado atual aponta o ato que o definiu (ValorExtraido.ato_origem).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from arquiteto_auditor.dominio.modelos import Evidencia, ValorExtraido


class TipoAto(StrEnum):
    """Tipos de ato entendidos pelo software. OUTRO = não compreendido → pendência."""

    ABERTURA = "abertura"  # descrição inicial do imóvel e primeiro proprietário
    COMPRA_E_VENDA = "compra_e_venda"
    DOACAO = "doacao"
    RETIFICACAO = "retificacao"  # de área ou de medidas: muda a descrição do imóvel
    ALIENACAO_FIDUCIARIA = "alienacao_fiduciaria"
    HIPOTECA = "hipoteca"
    CANCELAMENTO = "cancelamento"  # cancela um ônus anterior
    ALTERACAO_DENOMINACAO = "alteracao_denominacao"  # nome da rua, numeração
    CONSTRUCAO = "construcao"
    OUTRO = "outro"


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AtoMatricula(_Modelo):
    codigo: str  # "R-1", "AV-2"... ("ABERTURA" para a descrição inicial)
    tipo: TipoAto
    data: date | None = None
    texto: str  # texto do ato, como lido
    evidencia: Evidencia
    confianca: float = Field(ge=0, le=1)


class MatriculaLida(_Modelo):
    arquivo: str
    numero: str | None = None
    atos: list[AtoMatricula] = Field(default_factory=list)
    estado_atual: dict[str, ValorExtraido] = Field(default_factory=dict)
    pendencias: list[str] = Field(default_factory=list)  # atos não compreendidos etc.
