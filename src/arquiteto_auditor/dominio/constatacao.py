"""Constatação de completude: algo exigido nas pranchas está presente, ausente ou alterado.

Fica no domínio porque passa da leitura das pranchas (Fase 6) para o motor de verificação
(Fase 9), que não depende da extração.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from arquiteto_auditor.dominio.modelos import Evidencia


class Situacao(StrEnum):
    PRESENTE = "presente"
    AUSENTE = "ausente"
    ALTERADA = "alterada"  # documento alterado depois de assinado


@dataclass(frozen=True)
class Constatacao:
    chave: str  # chave do catálogo (COTA_INDEFINIDA, NORTE_INDICADO, ID_PROPRIETARIO...)
    situacao: Situacao
    escopo: str | None = None  # ex.: "elemento=recuo_fundos"
    evidencias: tuple[Evidencia, ...] = field(default_factory=tuple)
    motivo: str = ""
