"""Avalia a leitura do memorial descritivo (Fase 7) na base sintética.

Uso:  .venv/Scripts/python scripts/avaliar_memorial.py [--reservados] [--detalhes] [conjunto ...]

A verdade é o que o memorial de cada conjunto mostra (avaliacao/verdade_memorial.py). Para
cada campo: certo, errado, não encontrado ou falso valor (o memorial não mostra, mas algo foi
extraído). Valor errado que não ficou pendente de confirmação é o pior erro (precisa ser 0).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from avaliar_pranchas import comparar  # noqa: E402

from arquiteto_auditor.avaliacao.verdade_memorial import (  # noqa: E402
    CAMPOS_IDENTIFICACAO_MEMORIAL,
    CAMPOS_MEMORIAL,
    verdade_do_memorial,
)
from arquiteto_auditor.dominio.modelos import StatusConfirmacao  # noqa: E402
from arquiteto_auditor.extracao.memorial import ler_memorial  # noqa: E402
from arquiteto_auditor.ingestao.leitor import LeitorPDF  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados, detalhes = "--reservados" in argumentos, "--detalhes" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    leitor = LeitorPDF()
    por_campo: dict[str, Counter] = {campo: Counter() for campo in CAMPOS_MEMORIAL}
    pendencias = Counter()
    conjuntos = []
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        conjuntos.append(pasta.name)
        especificacao = json.loads((pasta / "especificacao.json").read_text(encoding="utf-8"))
        ocr = json.loads((pasta / "verdade_ocr.json").read_text(encoding="utf-8"))
        verdade = verdade_do_memorial(especificacao, narrativo=any("imagem" in k for k in ocr))
        extraidos = ler_memorial(leitor.ler(pasta / "memorial.pdf"))
        for campo in CAMPOS_MEMORIAL:
            valor = extraidos.get(campo)
            resultado = comparar(valor.valor if valor else None, verdade[campo])
            por_campo[campo][resultado] += 1
            pendente = bool(valor and valor.status == StatusConfirmacao.PENDENTE)
            pendencias["pendentes"] += pendente
            if resultado in ("errado", "falso valor") and not pendente:
                pendencias["errados sem pendência"] += 1
            if detalhes and resultado != "certo":
                print(f"   {pasta.name} {campo}: esperado {verdade[campo]!r}, "
                      f"lido {valor.valor if valor else None!r} ({resultado}"
                      f"{', pendente' if pendente else ''})")

    print(f"Conjuntos: {', '.join(conjuntos)}\n")
    for titulo, campos in (("Identificação", CAMPOS_IDENTIFICACAO_MEMORIAL),
                           ("Numéricos", [c for c in CAMPOS_MEMORIAL
                                          if c not in CAMPOS_IDENTIFICACAO_MEMORIAL])):
        total = Counter()
        for campo in campos:
            total.update(por_campo[campo])
        avaliados = sum(total.values())
        print(f"{titulo}: {total['certo']}/{avaliados} certos "
              f"({100 * total['certo'] / max(avaliados, 1):.1f}%) — errados {total['errado']}, "
              f"não encontrados {total['nao encontrado']}, falsos valores {total['falso valor']}")
    print(f"Pendentes: {pendencias['pendentes']}; errados SEM pendência: "
          f"{pendencias['errados sem pendência']} (precisa ser 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
