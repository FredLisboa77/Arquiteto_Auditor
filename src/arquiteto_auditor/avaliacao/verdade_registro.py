"""O que a matrícula e a escritura sintéticas dizem: a verdade para medir a Fase 7.

Sai da especificacao.json gravada pelo gerador (dados_sinteticos/geradores/registro.py e
escritura.py): a lista de atos (código, tipo, data), o estado atual do imóvel depois de todos
os atos (área, proprietário, ônus ainda ativos) e o que a escritura descreve.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from arquiteto_auditor.dominio.registro import TipoAto

# Título do ato no gerador → tipo
_TIPO_DO_TITULO = {
    "COMPRA E VENDA": TipoAto.COMPRA_E_VENDA,
    "RETIFICACAO DE AREA": TipoAto.RETIFICACAO,
    "ALIENACAO FIDUCIARIA": TipoAto.ALIENACAO_FIDUCIARIA,
    "CANCELAMENTO": TipoAto.CANCELAMENTO,
    "ALTERACAO DE DENOMINACAO": TipoAto.ALTERACAO_DENOMINACAO,
}
_ATO = re.compile(r"^(?P<codigo>(?:R|AV)-\d+) (?P<titulo>.+) \((?P<data>\d{2}/\d{2}/\d{4})\)$")


def _sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.upper())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


@dataclass(frozen=True)
class AtoEsperado:
    codigo: str  # "R-1", "AV-2"...
    tipo: TipoAto
    data: str  # dd/mm/aaaa


@dataclass(frozen=True)
class VerdadeRegistro:
    atos: list[AtoEsperado]
    area_atual: float
    proprietario_atual: str
    onus_ativos: list[str] = field(default_factory=list)  # ex.: ["R-3"]
    escritura_area: float | None = None
    escritura_data: str | None = None  # data da lavratura
    escritura_comprador: str | None = None


def verdade_do_registro(especificacao: dict) -> VerdadeRegistro:
    registrais = especificacao["documentos_registrais"]
    matricula, escritura = registrais["matricula"], registrais.get("escritura") or {}
    atos = []
    for descricao in matricula["atos"]:
        m = _ATO.match(descricao)
        if m is None:
            raise ValueError(f"ato fora do formato esperado: {descricao!r}")
        atos.append(AtoEsperado(m["codigo"], _TIPO_DO_TITULO[_sem_acentos(m["titulo"])],
                                m["data"]))
    return VerdadeRegistro(
        atos=atos,
        area_atual=matricula["area_atual"],
        proprietario_atual=matricula["proprietario_atual"],
        onus_ativos=[o.split("/")[0] for o in matricula["onus_ativos"]],
        escritura_area=escritura.get("area_descrita"),
        escritura_data=escritura.get("data"),
        escritura_comprador=matricula["proprietario_atual"] if escritura else None,
    )
