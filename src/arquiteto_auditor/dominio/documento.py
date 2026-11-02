"""Documento lido: páginas com uma lista única de palavras, cada uma com posição e confiança.

É o resultado da ingestão (Fase 5) e a entrada da extração (Fases 6 a 8). A mesma lista junta
as três fontes de texto de um PDF (docs/06-calibracao-exemplos-reais.md §1 e §6):
- "vetorial": texto selecionável;
- "comentario": texto guardado em comentários do PDF (ex.: texto SHX exportado pelo AutoCAD);
- "ocr": texto lido de imagem (página escaneada ou imagem embutida numa página vetorial).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from arquiteto_auditor.dominio.modelos import TipoDocumento


class OrigemPalavra(StrEnum):
    VETORIAL = "vetorial"
    COMENTARIO = "comentario"
    OCR = "ocr"


class TipoPagina(StrEnum):
    VETORIAL = "vetorial"  # PDF "nascido digital" (texto e/ou desenho)
    ESCANEADA = "escaneada"  # a página é uma imagem


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Palavra(_Modelo):
    texto: str = Field(min_length=1)
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 em pontos, origem no canto superior
    confianca: float = Field(ge=0, le=1)  # 1.0 para texto vetorial e comentários
    origem: OrigemPalavra
    linha: int = 0  # palavras com o mesmo número estão na mesma linha (dentro do bloco)
    bloco: int = 0

    @field_validator("bbox")
    @classmethod
    def _bbox_ordenada(cls, bbox):
        if bbox[2] < bbox[0] or bbox[3] < bbox[1]:
            raise ValueError("bbox deve ser (x0, y0, x1, y1) com x1 >= x0 e y1 >= y0")
        return bbox


class PaginaLida(_Modelo):
    numero: int = Field(ge=1)
    largura: float  # pontos (1 pt = 1/72 polegada)
    altura: float
    tipo: TipoPagina
    palavras: list[Palavra] = Field(default_factory=list)
    imagens_lidas_por_ocr: int = 0  # imagens embutidas lidas por OCR numa página vetorial
    desenhos: int = 0  # elementos de desenho vetorial (pranchas têm milhares)
    dpi_imagem: int | None = None  # resolução da imagem, quando a página é escaneada
    # Linhas de cota desenhadas (x0, y0, x1, y1), em pontos — ingestao/geometria.py
    cotas_desenhadas: list[tuple[float, float, float, float]] = Field(default_factory=list)

    @property
    def texto(self) -> str:
        """Texto da página em ordem de leitura (blocos, linhas, palavras)."""
        linhas: dict[tuple[int, int], list[Palavra]] = {}
        for palavra in self.palavras:
            linhas.setdefault((palavra.bloco, palavra.linha), []).append(palavra)
        return "\n".join(" ".join(p.texto for p in grupo)
                         for _, grupo in sorted(linhas.items()))

    def confianca_media(self) -> float | None:
        if not self.palavras:
            return None
        return sum(p.confianca for p in self.palavras) / len(self.palavras)


class AssinaturaDigital(_Modelo):
    """Assinatura digital embutida no PDF (ingestao/assinaturas.py). Sem CPF do titular."""

    campo: str | None = None  # nome do campo de assinatura no PDF
    titular: str | None = None
    emissor: str | None = None
    data: datetime | None = None  # data informada pelo assinante
    integra: bool  # o conteúdo assinado não mudou
    cobre_arquivo_inteiro: bool  # nada foi salvo no arquivo depois desta assinatura
    confiavel: bool  # cadeia até uma raiz confiável (offline: só com raízes guardadas)
    erro: str | None = None  # tipo do erro, se a assinatura não pôde ser conferida


class DocumentoLido(_Modelo):
    arquivo: str  # nome do arquivo (sem a pasta)
    hash_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paginas: list[PaginaLida]
    tipo: TipoDocumento = TipoDocumento.OUTRO
    confianca_tipo: float = Field(default=0.0, ge=0, le=1)
    motivo_tipo: str | None = None  # por que o classificador escolheu esse tipo
    assinaturas: list[AssinaturaDigital] = Field(default_factory=list)

    @property
    def escaneado(self) -> bool:
        return bool(self.paginas) and all(p.tipo == TipoPagina.ESCANEADA for p in self.paginas)
