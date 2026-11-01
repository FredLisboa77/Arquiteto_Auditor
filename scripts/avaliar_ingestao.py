"""Avalia a ingestão (Fase 5) na base sintética: tipo de página, tipo de documento e OCR.

Uso:  .venv\\Scripts\\python scripts\\avaliar_ingestao.py [--reservados] [conjunto ...]

Sem --reservados, usa só os conjuntos de desenvolvimento (os reservados medem, no fim, se as
regras generalizam — docs/05-avaliacao.md §4). A verdade vem da própria base:
- página escaneada = arquivo listado em verdade_ocr.json;
- tipo do documento = nome do arquivo (prancha*, matricula, escritura, memorial...);
- texto correto de cada página escaneada (e do quadro-imagem do memorial) = verdade_ocr.json.

Além do CER, mostra separados os erros no texto do documento e o texto lido a mais
(carimbos, selos e rubricas estão na imagem, mas não na verdade).

O OCR fica em cache (dados_privados/cache/ocr): a 1ª execução demora; as seguintes, não.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from arquiteto_auditor.avaliacao.ocr import (  # noqa: E402
    distancia_edicao,
    normalizar_espacos,
    separar_erros,
)
from arquiteto_auditor.dominio.documento import OrigemPalavra, TipoPagina  # noqa: E402
from arquiteto_auditor.ingestao.leitor import BLOCO_IMAGENS, LeitorPDF  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"
TIPO_PELO_NOME = {"prancha": "prancha", "matricula": "matricula", "escritura": "escritura",
                  "memorial": "memorial", "lei_municipal": "lei_municipal",
                  "norma_condominio": "norma_condominio"}


def tipo_esperado(nome: str) -> str:
    return next(t for prefixo, t in TIPO_PELO_NOME.items() if nome.startswith(prefixo))


@dataclass
class Resultado:
    paginas: int = 0
    paginas_certas: int = 0
    documentos: int = 0
    documentos_certos: int = 0
    erros_tipo: list[str] = field(default_factory=list)
    erros_pagina: list[str] = field(default_factory=list)
    # grupo → [edições, caracteres, erros no texto verdadeiro, caracteres a mais]
    ocr: dict[str, list[int]] = field(default_factory=dict)
    ocr_por_documento: list[tuple[str, float]] = field(default_factory=list)

    def somar_ocr(self, grupo: str, medida: tuple[int, int, int, int]) -> None:
        total = self.ocr.setdefault(grupo, [0, 0, 0, 0])
        for i, valor in enumerate(medida):
            total[i] += valor


def _medir(lido: str, verdade: str) -> tuple[int, int, int, int]:
    """(edições, caracteres da verdade, erros no texto verdadeiro, caracteres a mais)."""
    erros, a_mais = separar_erros(lido, verdade)
    verdade, lido = normalizar_espacos(verdade), normalizar_espacos(lido)
    return distancia_edicao(lido, verdade), len(verdade), erros, a_mais


def avaliar(conjuntos: list[Path], leitor: LeitorPDF) -> Resultado:
    r = Resultado()
    for pasta in conjuntos:
        especificacao = json.loads((pasta / "especificacao.json").read_text(encoding="utf-8"))
        verdade = json.loads((pasta / "verdade_ocr.json").read_text(encoding="utf-8"))
        qualidade_matricula = especificacao["documentos_registrais"]["matricula"]["qualidade"]
        for pdf in sorted(pasta.glob("*.pdf")):
            lido = leitor.ler(pdf)
            nome = f"{pasta.name}/{pdf.name}"
            r.documentos += 1
            esperado = tipo_esperado(pdf.name)
            if lido.tipo.value == esperado:
                r.documentos_certos += 1
            else:
                r.erros_tipo.append(f"{nome}: esperado {esperado}, obtido {lido.tipo.value} "
                                    f"({lido.motivo_tipo})")
            escaneado = pdf.name in verdade
            for pagina in lido.paginas:
                r.paginas += 1
                certo = (pagina.tipo == TipoPagina.ESCANEADA) == escaneado
                r.paginas_certas += certo
                if not certo:
                    r.erros_pagina.append(f"{nome} pág. {pagina.numero}: {pagina.tipo.value}")
            if escaneado:
                medida = [0, 0, 0, 0]
                for pagina, correto in zip(lido.paginas, verdade[pdf.name], strict=True):
                    medida = [a + b for a, b in zip(medida, _medir(pagina.texto, correto),
                                                    strict=True)]
                grupo = esperado
                if esperado == "matricula":
                    grupo = f"matricula ({qualidade_matricula})"
                r.somar_ocr(grupo, tuple(medida))
                r.ocr_por_documento.append((nome, medida[0] / max(medida[1], 1)))
            chave_imagem = f"{pdf.name} (imagem do quadro de áreas)"
            if chave_imagem in verdade:
                palavras = [p.texto for p in lido.paginas[0].palavras
                            if p.origem == OrigemPalavra.OCR and p.bloco >= BLOCO_IMAGENS]
                medida = _medir(" ".join(palavras), " ".join(verdade[chave_imagem]))
                r.somar_ocr("memorial (quadro como imagem)", medida)
                r.ocr_por_documento.append((nome + " [quadro-imagem]",
                                            medida[0] / max(medida[1], 1)))
    return r


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados = "--reservados" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    conjuntos = []
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        conjuntos.append(pasta)

    leitor = LeitorPDF()
    inicio = time.time()
    r = avaliar(conjuntos, leitor)
    print(f"Conjuntos: {', '.join(p.name for p in conjuntos)}  ({time.time() - inicio:.0f} s)\n")
    print(f"Tipo de página (vetorial × escaneada): {r.paginas_certas}/{r.paginas} "
          f"({100 * r.paginas_certas / r.paginas:.1f}%)")
    for erro in r.erros_pagina:
        print(f"   ✗ {erro}")
    print(f"Tipo de documento: {r.documentos_certos}/{r.documentos} "
          f"({100 * r.documentos_certos / r.documentos:.1f}%)")
    for erro in r.erros_tipo:
        print(f"   ✗ {erro}")
    print("\nOCR — taxa de erro de caracteres (CER), por grupo:")
    print(f"   {'':32s} {'CER':>7s}  {'texto errado':>12s}  {'texto a mais':>12s}")
    for grupo, (edicoes, caracteres, erros, a_mais) in sorted(r.ocr.items()):
        taxas = [100 * valor / caracteres for valor in (edicoes, erros, a_mais)]
        print(f"   {grupo:32s} {taxas[0]:6.2f}%  {taxas[1]:11.2f}%  {taxas[2]:11.2f}%"
              f"   ({caracteres} caracteres)")
    print("   texto errado = caracteres do documento lidos errado ou perdidos;\n"
          "   texto a mais = lido além da verdade (carimbos, selo, \"CÓPIA\", rabiscos).")
    print("\nOCR — por documento:")
    for nome, taxa in r.ocr_por_documento:
        print(f"   {nome:45s} {100 * taxa:6.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
