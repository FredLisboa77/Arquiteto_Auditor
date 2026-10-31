"""Diagnóstico de PDFs reais — mostra APENAS estatísticas, nunca o conteúdo.

Uso:  .venv\\Scripts\\python scripts\\diagnosticar_pdfs.py [pasta]
      (padrão: dados_privados\\documentos_reais)

Para cada PDF (identificado só como "arquivo 1", "arquivo 2"...): número de páginas, tamanho
da folha, quantidade de caracteres extraíveis, tipos de fonte, desenhos vetoriais, imagens,
assinaturas e o software que gerou o arquivo (só se for um nome conhecido).

Serve para conferir o risco R1 (docs/01-viabilidade.md): texto do AutoCAD exportado como
desenho (fontes SHX) em vez de texto selecionável.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

from arquiteto_auditor.dominio.numeros import encontrar_valores

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = RAIZ / "dados_privados" / "documentos_reais"
MM = 25.4 / 72

SOFTWARES_CONHECIDOS = (
    "AutoCAD", "Revit", "ArchiCAD", "SketchUp", "LayOut", "Vectorworks", "BricsCAD", "ZWCAD",
    "DWG TrueView", "DraftSight", "Bluebeam", "Acrobat", "PDF24", "Microsoft", "Ghostscript",
    "Nitro", "Foxit", "PDFCreator", "QCAD", "LibreCAD", "FreeCAD", "ReportLab", "iText",
)


def software_produtor(texto: str) -> str:
    """Só devolve nomes de software conhecidos (metadados podem ter nomes e caminhos)."""
    if not texto:
        return "não informado"
    if "Arquiteto Auditor" in texto:
        return "base sintética"
    for nome in SOFTWARES_CONHECIDOS:
        if re.search(re.escape(nome), texto, re.IGNORECASE):
            return nome
    return "outro"


_NUMERO_ISOLADO = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def _ocupacao_texto(pagina: pymupdf.Page, palavras: list) -> float:
    """Fração das células de uma grade 10×10 que contêm ao menos uma palavra."""
    if not palavras:
        return 0.0
    largura, altura = pagina.rect.width, pagina.rect.height
    celulas = set()
    for x0, y0, x1, y1, *_ in palavras:
        coluna = min(int((x0 + x1) / 2 / largura * 10), 9)
        linha = min(int((y0 + y1) / 2 / altura * 10), 9)
        celulas.add((coluna, linha))
    return len(celulas) / 100


def _diagnosticar_pagina(pagina: pymupdf.Page) -> dict:
    texto = pagina.get_text()
    caracteres = len(re.sub(r"\s", "", texto))
    palavras = pagina.get_text("words")
    lista_desenhos = pagina.get_drawings()
    desenhos = len(lista_desenhos)
    # Traço com até 4 mm no maior lado: tamanho típico de uma letra desenhada (fonte SHX).
    tracos_pequenos = sum(
        1 for d in lista_desenhos if max(d["rect"].width, d["rect"].height) * MM <= 4
    )
    anotacoes = list(pagina.annots())
    # Texto guardado nos comentários (o AutoCAD pode pôr ali o texto em fonte SHX).
    conteudos = [(a.info.get("content") or "").strip() for a in anotacoes]
    tokens_anotacoes = [t for c in conteudos for t in c.split()]
    area_pagina = abs(pagina.rect)
    area_imagens = 0.0
    for imagem in pagina.get_image_info():
        area_imagens += abs(pymupdf.Rect(imagem["bbox"]) & pagina.rect)
    cobertura = min(area_imagens / area_pagina, 1.0) if area_pagina else 0.0
    fontes = pagina.get_fonts()
    return {
        "largura_mm": round(pagina.rect.width * MM),
        "altura_mm": round(pagina.rect.height * MM),
        "caracteres": caracteres,
        "palavras": len(palavras),
        "palavras_numericas": sum(1 for p in palavras if _NUMERO_ISOLADO.match(p[4])),
        "ocupacao_texto": _ocupacao_texto(pagina, palavras),
        "valores_com_unidade": sum(1 for v in encontrar_valores(texto) if v.unidade),
        "desenhos": desenhos,
        "tracos_pequenos": tracos_pequenos,
        "anotacoes": len(anotacoes),
        "tipos_de_anotacao": sorted({a.type[1] for a in anotacoes}),
        "anotacoes_com_texto": sum(1 for c in conteudos if c),
        "caracteres_em_anotacoes": sum(len(re.sub(r"\s", "", c)) for c in conteudos),
        "numeros_em_anotacoes": sum(1 for t in tokens_anotacoes if _NUMERO_ISOLADO.match(t)),
        "imagens": len(pagina.get_image_info()),
        "cobertura_imagens": round(cobertura, 2),
        "tipos_de_fonte": sorted({f[2] for f in fontes}),
        "fontes_type3": sum(1 for f in fontes if f[2] == "Type3"),
        "assinaturas": sum(1 for w in pagina.widgets() if w.field_type_string == "Signature"),
        # Muitos traços e quase nenhum texto: texto provavelmente virou desenho (fonte SHX).
        "suspeita_texto_como_desenho": desenhos > 2000 and caracteres < 200,
        # Página dominada por imagem e sem texto: provavelmente escaneada.
        "suspeita_escaneada": cobertura > 0.5 and caracteres < 100,
    }


def diagnosticar_pasta(pasta: Path) -> list[dict]:
    resultado = []
    for numero, caminho in enumerate(sorted(Path(pasta).rglob("*.pdf")), start=1):
        item = {"arquivo": f"arquivo {numero}", "erro": None, "paginas": 0, "por_pagina": []}
        try:
            with pymupdf.open(caminho) as documento:
                item["paginas"] = len(documento)
                item["software"] = software_produtor(
                    f"{documento.metadata.get('creator', '')} "
                    f"{documento.metadata.get('producer', '')}".strip())
                item["por_pagina"] = [_diagnosticar_pagina(p) for p in documento]
        except Exception as erro:  # arquivo corrompido, protegido por senha etc.
            item["erro"] = type(erro).__name__
        resultado.append(item)
    return resultado


def formatar_relatorio(arquivos: list[dict]) -> str:
    linhas = [f"Diagnóstico de {len(arquivos)} arquivo(s) PDF — somente estatísticas", ""]
    alertas = 0
    for item in arquivos:
        if item["erro"]:
            linhas.append(f"{item['arquivo']}: não foi possível abrir ({item['erro']})")
            continue
        linhas.append(f"{item['arquivo']}: {item['paginas']} página(s), "
                      f"software: {item.get('software', '?')}")
        for i, p in enumerate(item["por_pagina"], start=1):
            sinais = []
            if p["suspeita_texto_como_desenho"]:
                sinais.append("SUSPEITA: texto como desenho")
            if p["suspeita_escaneada"]:
                sinais.append("SUSPEITA: página escaneada")
            if p["fontes_type3"]:
                sinais.append(f"{p['fontes_type3']} fonte(s) Type3")
            alertas += bool(sinais)
            tipos_anotacao = ", ".join(p["tipos_de_anotacao"]) or "—"
            linhas += [
                f"   pág. {i}: {p['largura_mm']}×{p['altura_mm']} mm | "
                f"fontes: {', '.join(p['tipos_de_fonte']) or 'nenhuma'} | "
                f"{p['assinaturas']} assinatura(s)"
                + (f"  ⚠ {'; '.join(sinais)}" if sinais else ""),
                f"      texto: {p['caracteres']} caracteres, {p['palavras']} palavras, "
                f"{p['palavras_numericas']} números isolados, "
                f"{p['valores_com_unidade']} valores com unidade, "
                f"texto em {p['ocupacao_texto']:.0%} da folha",
                f"      desenho: {p['desenhos']} elementos, {p['tracos_pequenos']} traços "
                f"pequenos (≤ 4 mm) | {p['imagens']} imagem(ns) "
                f"({p['cobertura_imagens']:.0%} da folha) | "
                f"{p['anotacoes']} comentário(s) ({tipos_anotacao})",
                f"      comentários: {p['anotacoes_com_texto']} com texto, "
                f"{p['caracteres_em_anotacoes']} caracteres, "
                f"{p['numeros_em_anotacoes']} números isolados",
            ]
    linhas += ["", f"Páginas com alerta: {alertas}"]
    return "\n".join(linhas)


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    pasta = Path(argumentos[0]) if argumentos else PASTA_PADRAO
    if not pasta.is_dir():
        print(f"Pasta não encontrada: {pasta}")
        return 1
    print(formatar_relatorio(diagnosticar_pasta(pasta)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
