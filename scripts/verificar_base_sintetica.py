"""Confere a base sintética inteira: nenhum CPF/CNPJ válido, marca de fictício e gabaritos.

Uso:  .venv\\Scripts\\python scripts\\verificar_base_sintetica.py [pasta]
      (padrão: dados_sinteticos\\projetos)

Procura CPF e CNPJ em TODO o texto da base: arquivos JSON, texto selecionável dos PDFs,
comentários dos PDFs (texto SHX do estilo AutoCAD) e o texto impresso dos escaneados
(verdade_ocr.json). Os dados sintéticos usam de propósito dígitos verificadores inválidos;
um CPF ou CNPJ válido indicaria dado real (ou um defeito no gerador).

Também confere que todo PDF se declara fictício (no texto, nos comentários, no texto dos
escaneados ou nos metadados) e que todo gabarito.json é válido.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))

from arquiteto_auditor.avaliacao.gabarito import GabaritoInvalido, carregar_gabarito  # noqa: E402
from scripts.verificar_vazamento import PADRAO_CPF, cpf_valido  # noqa: E402

PASTA_PADRAO = RAIZ / "dados_sinteticos" / "projetos"
PADRAO_CNPJ = re.compile(r"(?<!\d)(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?!\d)")
MARCAS = ("FICTÍCIO", "FICTICIO", "SINTÉTIC", "SINTETIC")


def cnpj_valido(digitos: str) -> bool:
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    numeros = [int(d) for d in digitos]
    for tamanho, pesos in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
                           (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        resto = sum(d * p for d, p in zip(numeros[:tamanho], pesos, strict=True)) % 11
        if numeros[tamanho] != (0 if resto < 2 else 11 - resto):
            return False
    return True


def documentos_validos(texto: str) -> list[str]:
    """CPFs e CNPJs com dígitos verificadores válidos encontrados no texto."""
    achados = ["CPF " + "".join(m.groups()) for m in PADRAO_CPF.finditer(texto)
               if cpf_valido("".join(m.groups()))]
    achados += ["CNPJ " + "".join(m.groups()) for m in PADRAO_CNPJ.finditer(texto)
                if cnpj_valido("".join(m.groups()))]
    return achados


def texto_do_pdf(caminho: Path) -> tuple[str, str]:
    """(texto selecionável + comentários, metadados) de um PDF."""
    partes = []
    with pymupdf.open(caminho) as documento:
        for pagina in documento:
            partes.append(pagina.get_text())
            partes.extend(a.info.get("content", "") for a in pagina.annots())
        metadados = " ".join(str(v) for v in documento.metadata.values() if v)
    return "\n".join(partes), metadados


@dataclass
class Relatorio:
    conjuntos: int = 0
    arquivos: int = 0
    cpfs_conferidos: int = 0
    problemas: list[str] = field(default_factory=list)


def verificar(pasta: Path) -> Relatorio:
    relatorio = Relatorio()
    for conjunto in sorted(p for p in pasta.iterdir() if p.is_dir()):
        relatorio.conjuntos += 1
        verdade_ocr = {}
        if (conjunto / "verdade_ocr.json").exists():
            verdade_ocr = json.loads((conjunto / "verdade_ocr.json").read_text(encoding="utf-8"))
        for arquivo in sorted(conjunto.iterdir()):
            relatorio.arquivos += 1
            nome = f"{conjunto.name}/{arquivo.name}"
            if arquivo.suffix == ".pdf":
                texto, metadados = texto_do_pdf(arquivo)
                texto += "\n" + "\n".join(verdade_ocr.get(arquivo.name, []))
                if not any(m in (texto + metadados).upper() for m in MARCAS):
                    relatorio.problemas.append(f"{nome}: sem marca de documento fictício")
            elif arquivo.suffix == ".json":
                texto = arquivo.read_text(encoding="utf-8")
            else:
                continue
            relatorio.cpfs_conferidos += len(PADRAO_CPF.findall(texto))
            for achado in documentos_validos(texto):
                relatorio.problemas.append(f"{nome}: {achado.split()[0]} com dígitos válidos "
                                           f"(possível dado real)")
        try:
            carregar_gabarito(conjunto / "gabarito.json")
        except (GabaritoInvalido, FileNotFoundError) as erro:
            relatorio.problemas.append(f"{conjunto.name}: gabarito inválido ou ausente ({erro})")
    return relatorio


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    pasta = Path(argumentos[0]) if argumentos else PASTA_PADRAO
    relatorio = verificar(pasta)
    print(f"Base sintética: {relatorio.conjuntos} conjunto(s), {relatorio.arquivos} arquivo(s), "
          f"{relatorio.cpfs_conferidos} número(s) com formato de CPF conferido(s).")
    if relatorio.problemas:
        print(f"\n{len(relatorio.problemas)} PROBLEMA(S):")
        for problema in relatorio.problemas:
            print(f"  - {problema}")
        return 1
    print("OK: nenhum CPF ou CNPJ válido; todos os PDFs se declaram fictícios; gabaritos válidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
