"""Classes de domínio: a "linguagem comum" de todo o sistema.

Regras que valem em todo lugar (ver CLAUDE.md):
- todo valor lido de documento carrega Evidencia (arquivo, página, trecho) e confiança;
- itens conclusivos ("atende", "não atende", "divergente") exigem evidência;
- "não foi possível verificar" exige o motivo.

Projeto e Relatorio entram nas Fases 11 e 12, quando forem usados.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PADRAO_CHAVE = r"^[A-Z][A-Z0-9_]*$"


class OrigemValor(StrEnum):
    VETORIAL = "vetorial"  # texto selecionável do PDF
    OCR = "ocr"  # lido de imagem
    LLM = "llm"  # interpretado pelo modelo de linguagem (sempre com citação)
    REVISOR = "revisor"  # informado/corrigido por você na tela de confirmação
    CALCULADO = "calculado"  # calculado pelo código a partir de outros valores


class StatusConfirmacao(StrEnum):
    AUTOMATICO = "automatico"
    PENDENTE = "pendente_confirmacao"
    CONFIRMADO = "confirmado"
    CORRIGIDO = "corrigido_pelo_revisor"


class StatusItem(StrEnum):
    ATENDE = "atende"
    NAO_ATENDE = "nao_atende"
    DIVERGENTE = "divergente"
    NAO_VERIFICAVEL = "nao_verificavel"


class ResultadoComparacao(StrEnum):
    """Situação de um item em relação à rodada anterior (R00 → R01)."""

    RESOLVIDO = "resolvido"
    PENDENTE = "pendente"
    NOVO = "novo"
    NAO_VERIFICAVEL_AGORA = "nao_verificavel_agora"


class TipoDocumento(StrEnum):
    PRANCHA = "prancha"
    MATRICULA = "matricula"
    ESCRITURA = "escritura"
    MEMORIAL = "memorial"
    LEI_MUNICIPAL = "lei_municipal"
    CONSULTA_PREVIA = "consulta_previa"
    NORMA_CONDOMINIO = "norma_condominio"
    OUTRO = "outro"


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidencia(_Modelo):
    """Onde um valor foi encontrado. Sem evidência, não há conclusão."""

    documento: str = Field(min_length=1)  # nome do arquivo
    pagina: int = Field(ge=1)
    trecho: str = Field(min_length=1)  # texto literal do documento
    prancha: str | None = None  # ex.: "01/05 — Planta de situação"
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 na página
    confianca_ocr: float | None = Field(default=None, ge=0, le=1)

    @field_validator("bbox")
    @classmethod
    def _bbox_ordenada(cls, bbox):
        if bbox is not None and (bbox[2] < bbox[0] or bbox[3] < bbox[1]):
            raise ValueError("bbox deve ser (x0, y0, x1, y1) com x1 >= x0 e y1 >= y0")
        return bbox


class ValorExtraido(_Modelo):
    campo: str = Field(pattern=PADRAO_CHAVE)
    valor: float | str
    unidade: str | None = None
    origem: OrigemValor
    confianca: float = Field(ge=0, le=1)
    evidencias: list[Evidencia] = Field(default_factory=list)
    status: StatusConfirmacao = StatusConfirmacao.AUTOMATICO
    calculado_de: list[str] = Field(default_factory=list)  # campos usados no cálculo
    ato_origem: str | None = None  # ato da matrícula que definiu o valor (ex.: "AV-2")
    observacao: str | None = None

    @model_validator(mode="after")
    def _rastreabilidade(self):
        if self.origem == OrigemValor.CALCULADO:
            if not self.calculado_de:
                raise ValueError("valor calculado precisa informar 'calculado_de'")
        elif self.origem == OrigemValor.REVISOR:
            if not self.observacao:
                raise ValueError("valor informado pelo revisor precisa de 'observacao'")
        elif not self.evidencias:
            raise ValueError(f"valor de origem '{self.origem}' precisa de ao menos uma evidência")
        return self

    def precisa_confirmacao(self, limiar: float) -> bool:
        if self.status in (StatusConfirmacao.CONFIRMADO, StatusConfirmacao.CORRIGIDO):
            return False
        return self.status == StatusConfirmacao.PENDENTE or self.confianca < limiar


class Parametro(_Modelo):
    """Limite extraído da legislação municipal ou das normas do condomínio."""

    chave: str = Field(pattern=PADRAO_CHAVE)
    valor: float
    unidade: str | None = None
    fonte: Literal["prefeitura", "condominio"]
    limite: Literal["minimo", "maximo"]
    zona: str | None = None
    condicao: str | None = None  # ex.: "para lotes com testada < 12 m"
    confianca: float = Field(ge=0, le=1)
    evidencias: list[Evidencia] = Field(min_length=1)


class ItemVerificacao(_Modelo):
    chave: str = Field(pattern=PADRAO_CHAVE)
    escopo: str | None = None  # ex.: "pavimento=1", "elemento=testada_frontal"
    status: StatusItem
    mensagem: str = Field(min_length=1)
    valor_projeto: float | str | None = None
    limite: float | None = None
    margem: float | None = None
    sugestao: str | None = None
    evidencias: list[Evidencia] = Field(default_factory=list)
    observacoes: list[str] = Field(default_factory=list)  # ex.: conflito prefeitura × condomínio
    baixa_confianca: bool = False
    incluir_no_relatorio: bool = True

    @model_validator(mode="after")
    def _conclusao_exige_evidencia(self):
        if self.status != StatusItem.NAO_VERIFICAVEL and not self.evidencias:
            raise ValueError(f"item '{self.status}' precisa de ao menos uma evidência")
        return self

    @property
    def chave_estavel(self) -> tuple[str, str | None]:
        """Identifica o item entre rodadas (R00 → R01)."""
        return (self.chave, self.escopo)


class Rodada(_Modelo):
    """Uma rodada de análise; gera o relatório R00, R01, R02..."""

    codigo: str = Field(pattern=r"^R\d{2}$")
    revisao_projeto: str | None = None  # revisão indicada no carimbo das pranchas
    itens: list[ItemVerificacao] = Field(default_factory=list)
    emitida: bool = False  # depois de emitida, a rodada não muda mais

    def proximo_codigo(self) -> str:
        numero = int(re.sub(r"\D", "", self.codigo))
        return f"R{numero + 1:02d}"
