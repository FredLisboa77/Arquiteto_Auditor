"""Parâmetro urbanístico adotado para o lote (o que vale depois da hierarquia).

Fica no domínio (sem dependências externas) porque passa da extração (Fase 8) para o motor
de verificação (Fase 9), que não pode depender do LLM nem da leitura dos documentos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from arquiteto_auditor.dominio.modelos import StatusConfirmacao, ValorExtraido


@dataclass(frozen=True)
class ParametroAdotado:
    chave: str
    valor: ValorExtraido  # o valor que vale, com a evidência do documento de onde veio
    fonte: Literal["prefeitura", "condominio"]
    valor_condominio: ValorExtraido | None = None  # quando a prefeitura também define
    observacao: str | None = None

    @property
    def conflito(self) -> bool:
        return (self.fonte == "prefeitura" and self.valor_condominio is not None
                and not math.isclose(float(self.valor.valor),
                                     float(self.valor_condominio.valor), abs_tol=1e-6))

    @property
    def pendente(self) -> bool:
        return self.valor.status == StatusConfirmacao.PENDENTE
