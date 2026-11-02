"""Avalia a extração das pranchas (Fase 6) na base sintética.

Uso:  .venv/Scripts/python scripts/avaliar_pranchas.py [--reservados] [--detalhes] [conjunto ...]

Sem --reservados, usa só os conjuntos de desenvolvimento (docs/05-avaliacao.md §4). A verdade
é o que cada prancha mostra (avaliacao/verdade_pranchas.py). Para cada campo:
- certo: valor extraído igual ao mostrado (números com tolerância de 0,005);
- errado: valor diferente;
- não encontrado: a prancha mostra, mas nada foi extraído;
- falso valor: a prancha NÃO mostra (ex.: cota omitida), mas algo foi extraído.
Valores marcados "pendente de confirmação" contam pelo que são e aparecem à parte.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from arquiteto_auditor.avaliacao.verdade_pranchas import (  # noqa: E402
    CAMPOS,
    CAMPOS_IDENTIFICACAO,
    verdade_das_pranchas,
)
from arquiteto_auditor.dominio.modelos import StatusConfirmacao  # noqa: E402
from arquiteto_auditor.extracao.pranchas import extrair_pranchas  # noqa: E402
from arquiteto_auditor.ingestao.leitor import LeitorPDF  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"


def _texto(valor) -> str:
    sem_acento = unicodedata.normalize("NFD", str(valor).casefold())
    return " ".join("".join(c for c in sem_acento if not unicodedata.combining(c)).split())


def comparar(extraido, esperado) -> str:
    if esperado is None:
        return "certo" if extraido is None else "falso valor"
    if extraido is None:
        return "nao encontrado"
    if isinstance(esperado, float):
        ok = isinstance(extraido, int | float) and abs(extraido - esperado) <= 0.005
    else:
        ok = _texto(extraido) == _texto(esperado)
    return "certo" if ok else "errado"


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados, detalhes = "--reservados" in argumentos, "--detalhes" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    leitor = LeitorPDF()
    por_campo: dict[str, Counter] = {campo: Counter() for campo in CAMPOS}
    pendentes = Counter()
    conjuntos = []
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        conjuntos.append(pasta.name)
        especificacao = json.loads((pasta / "especificacao.json").read_text(encoding="utf-8"))
        verdade = verdade_das_pranchas(especificacao)
        documentos = [leitor.ler(pdf) for pdf in sorted(pasta.glob("prancha*.pdf"))]
        extraidos = extrair_pranchas(documentos)
        for campo in CAMPOS:
            valor = extraidos.get(campo)
            resultado = comparar(valor.valor if valor else None, verdade[campo])
            por_campo[campo][resultado] += 1
            if valor and valor.status == StatusConfirmacao.PENDENTE:
                pendentes[resultado] += 1
            if detalhes and resultado != "certo":
                print(f"   {pasta.name} {campo}: esperado {verdade[campo]!r}, "
                      f"extraído {valor.valor if valor else None!r} ({resultado})")

    print(f"Conjuntos: {', '.join(conjuntos)}\n")
    for titulo, campos in (("Identificação", CAMPOS_IDENTIFICACAO),
                           ("Numéricos", [c for c in CAMPOS if c not in CAMPOS_IDENTIFICACAO])):
        total = Counter()
        for campo in campos:
            total.update(por_campo[campo])
        avaliados = sum(total.values())
        print(f"{titulo}: {total['certo']}/{avaliados} certos "
              f"({100 * total['certo'] / max(avaliados, 1):.1f}%) — errados {total['errado']}, "
              f"não encontrados {total['nao encontrado']}, falsos valores {total['falso valor']}")
        for campo in campos:
            c = por_campo[campo]
            print(f"   {campo:22s} certos {c['certo']:2d}  errados {c['errado']:2d}  "
                  f"não encontrados {c['nao encontrado']:2d}  falsos {c['falso valor']:2d}")
    print(f"\nPendentes de confirmação: {sum(pendentes.values())} "
          f"(certos {pendentes['certo']}, errados {pendentes['errado']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
