"""Avalia a leitura da matrícula (Fase 7) na base sintética.

Uso:  .venv/Scripts/python scripts/avaliar_registro.py [--reservados] [--detalhes] [conjunto ...]

Sem --reservados, usa só os conjuntos de desenvolvimento (docs/05-avaliacao.md §4). A verdade
vem da especificacao.json (avaliacao/verdade_registro.py). Mede:
- atos: certo = mesmo código, mesmo tipo e mesma data; "a mais" = ato que não existe;
- estado atual: área, proprietário e ônus ativos, e se cada campo aponta o ato de origem;
  valor errado que não ficou pendente de confirmação é o pior erro (precisa ser zero).
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from arquiteto_auditor.avaliacao.verdade_registro import verdade_do_registro  # noqa: E402
from arquiteto_auditor.extracao.registro import ler_escritura, ler_matricula  # noqa: E402
from arquiteto_auditor.ingestao.leitor import LeitorPDF  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"


def _texto(valor) -> str:
    sem_acento = unicodedata.normalize("NFD", str(valor).casefold())
    return " ".join("".join(c for c in sem_acento if not unicodedata.combining(c)).split())


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados, detalhes = "--reservados" in argumentos, "--detalhes" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    leitor = LeitorPDF()
    atos, estado, escritura = Counter(), Counter(), Counter()
    conjuntos = []
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        conjuntos.append(pasta.name)
        verdade = verdade_do_registro(json.loads(
            (pasta / "especificacao.json").read_text(encoding="utf-8")))
        lida = ler_matricula(leitor.ler(pasta / "matricula.pdf"))

        obtidos = {(a.codigo, a.tipo, a.data.strftime("%d/%m/%Y") if a.data else None)
                   for a in lida.atos if a.codigo != "ABERTURA"}
        esperados = {(a.codigo, a.tipo, a.data) for a in verdade.atos}
        atos["esperados"] += len(esperados)
        atos["certos"] += len(esperados & obtidos)
        atos["a mais"] += len(obtidos - esperados)
        if detalhes:
            for ato in sorted(esperados - obtidos):
                print(f"   {pasta.name} ato não lido corretamente: {ato}")
            for ato in sorted(obtidos - esperados, key=str):
                print(f"   {pasta.name} ato a mais ou errado: {ato}")

        onus = ", ".join(verdade.onus_ativos) or "nenhum"
        for campo, esperado in (("TERRENO_AREA", verdade.area_atual),
                                ("PROPRIETARIO", verdade.proprietario_atual),
                                ("ONUS_ATIVOS", onus)):
            valor = lida.estado_atual.get(campo)
            estado["esperados"] += 1
            certo = valor is not None and (
                abs(valor.valor - esperado) <= 0.005 if isinstance(esperado, float)
                else _texto(valor.valor) == _texto(esperado))
            estado["certos"] += certo
            estado["com ato de origem"] += bool(valor and valor.ato_origem)
            pendente = bool(valor and valor.status == "pendente_confirmacao")
            estado["pendentes"] += pendente
            estado["errados automáticos"] += bool(valor) and not certo and not pendente
            if detalhes and not certo:
                print(f"   {pasta.name} {campo}: esperado {esperado!r}, "
                      f"lido {valor.valor if valor else None!r}")

        lida_escritura = ler_escritura(leitor.ler(pasta / "escritura.pdf"))
        for campo, esperado in (("TERRENO_AREA", verdade.escritura_area),
                                ("COMPRADOR", verdade.escritura_comprador),
                                ("DATA_LAVRATURA", verdade.escritura_data)):
            valor = lida_escritura.campos.get(campo)
            escritura["esperados"] += 1
            certo = valor is not None and (
                abs(valor.valor - esperado) <= 0.005 if isinstance(esperado, float)
                else _texto(valor.valor) == _texto(esperado))
            pendente = bool(valor and valor.status == "pendente_confirmacao")
            escritura["certos"] += certo
            escritura["pendentes"] += pendente
            escritura["errados automáticos"] += bool(valor) and not certo and not pendente
            if detalhes and not certo:
                print(f"   {pasta.name} escritura {campo}: esperado {esperado!r}, "
                      f"lido {valor.valor if valor else None!r}")

    print(f"Conjuntos: {', '.join(conjuntos)}\n")
    print(f"Atos: {atos['certos']}/{atos['esperados']} certos "
          f"({100 * atos['certos'] / max(atos['esperados'], 1):.1f}%); "
          f"{atos['a mais']} a mais ou errados")
    print(f"Estado atual: {estado['certos']}/{estado['esperados']} certos "
          f"({100 * estado['certos'] / max(estado['esperados'], 1):.1f}%); "
          f"{estado['com ato de origem']} com ato de origem; {estado['pendentes']} pendentes; "
          f"{estado['errados automáticos']} errados SEM pendência (precisa ser 0)")
    print(f"Escritura (área, comprador, data): {escritura['certos']}/{escritura['esperados']} "
          f"certos ({100 * escritura['certos'] / max(escritura['esperados'], 1):.1f}%); "
          f"{escritura['pendentes']} pendentes; "
          f"{escritura['errados automáticos']} errados SEM pendência (precisa ser 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
