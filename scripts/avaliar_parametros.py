"""Avalia a leitura dos parâmetros da lei e da norma do condomínio (Fase 8) na base sintética.

Uso:  .venv/Scripts/python scripts/avaliar_parametros.py [--reservados] [--sem-llm] [--detalhes]
                                                         [conjunto ...]

A verdade é o gabarito de cada conjunto (valores_esperados[chave]["prefeitura" ou
"condominio"]). Para cada valor: certo, errado, não encontrado ou falso valor (o documento
não define, mas algo foi extraído). Valor errado que não ficou pendente é o pior erro
(precisa ser 0). Também confere que o trecho de cada evidência existe no documento.

O LLM precisa do Ollama ligado; as respostas ficam em cache (dados_privados/cache/llm).
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from arquiteto_auditor.config import pasta_de_dados  # noqa: E402
from arquiteto_auditor.dominio.modelos import StatusConfirmacao  # noqa: E402
from arquiteto_auditor.extracao.parametros.extrator import ler_parametros  # noqa: E402
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido, normalizar  # noqa: E402
from arquiteto_auditor.ingestao.leitor import LeitorPDF  # noqa: E402
from arquiteto_auditor.llm.cliente import ClienteLLM  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"
DOCUMENTOS = (("lei_municipal.pdf", "prefeitura"), ("norma_condominio.pdf", "condominio"))


def _compacto(texto: str) -> str:
    return re.sub(r"\s+", "", normalizar(texto)).replace("…", "")


def trecho_existe(trecho: str, documento_compacto: str) -> bool:
    """O trecho (texto da evidência) existe no documento? Tabelas: cada célula existe."""
    partes = trecho.split(" | ") if " | " in trecho else [trecho]
    return all(_compacto(p) in documento_compacto for p in partes)


def comparar(extraido, esperado) -> str:
    if esperado is None:
        return "falso valor" if extraido is not None else "ausente certo"
    if extraido is None:
        return "não encontrado"
    return "certo" if abs(float(extraido) - float(esperado)) < 1e-6 else "errado"


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados = "--reservados" in argumentos
    detalhes, sem_llm = "--detalhes" in argumentos, "--sem-llm" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    leitor = LeitorPDF()
    cliente = None if sem_llm else ClienteLLM(pasta_cache=pasta_de_dados() / "cache" / "llm")
    if cliente and not cliente.disponivel():
        print("Ollama indisponível: rode com --sem-llm ou ligue o Ollama.")
        return 2

    contagem: dict[str, Counter] = {"prefeitura": Counter(), "condominio": Counter()}
    zonas, evidencias, pendencias, graves = Counter(), Counter(), Counter(), []
    inicio = time.time()
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        especificacao = json.loads((pasta / "especificacao.json").read_text(encoding="utf-8"))
        esperados = gabarito["valores_esperados"]
        area = esperados["LOTE_AREA_MIN"]["calculado"]  # na análise real: a da matrícula
        for arquivo, fonte in DOCUMENTOS:
            caminho = pasta / arquivo
            documento = leitor.ler(caminho)
            compacto = _compacto(TextoCorrido(documento).texto)
            lido = ler_parametros(caminho, documento, fonte, cliente=cliente,
                                  nome_condominio=especificacao["identificacao"]["condominio"],
                                  area_lote=area)
            if fonte == "prefeitura":
                zona = lido.zona.valor if lido.zona else None
                zonas["certa" if zona == gabarito["zona"] else "errada ou ausente"] += 1
            chaves = sorted(set(lido.valores) | {k for k, v in esperados.items() if fonte in v})
            for chave in chaves:
                valor = lido.valores.get(chave)
                resultado = comparar(valor.valor if valor else None,
                                     esperados.get(chave, {}).get(fonte))
                pendente = bool(valor and valor.status == StatusConfirmacao.PENDENTE)
                contagem[fonte][resultado] += 1
                pendencias[fonte] += pendente
                if valor:
                    for evidencia in valor.evidencias:
                        evidencias["literal" if trecho_existe(evidencia.trecho, compacto)
                                   else "NÃO encontrado no documento"] += 1
                if resultado in ("errado", "falso valor") and not pendente:
                    graves.append(f"{pasta.name} {fonte} {chave}")
                if detalhes and (resultado not in ("certo", "ausente certo") or pendente):
                    print(f"  {pasta.name} {fonte:10} {chave:16} {resultado:14} "
                          f"esperado={esperados.get(chave, {}).get(fonte)} "
                          f"lido={valor.valor if valor else None}"
                          f"{' (pendente)' if pendente else ''}"
                          f"{' — ' + valor.evidencias[0].trecho[:70] if valor else ''}")

    print(f"\nZona da lei: {dict(zonas)}")
    for fonte, c in contagem.items():
        total = c["certo"] + c["errado"] + c["não encontrado"]
        taxa = 100 * c["certo"] / total if total else 0.0
        print(f"{fonte:10}: {c['certo']}/{total} certos ({taxa:.1f}%) — {dict(c)}; "
              f"pendentes: {pendencias[fonte]}")
    print(f"Evidências: {dict(evidencias)}")
    print(f"Errados ou inventados SEM pendência: {len(graves)} {graves}")
    if cliente:
        print(f"Chamadas ao LLM fora do cache: {cliente.chamadas}")
    print(f"Tempo: {time.time() - inicio:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
