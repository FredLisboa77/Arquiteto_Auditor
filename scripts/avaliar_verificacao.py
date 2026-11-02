"""Avalia a análise completa (leitura + motor de verificação) contra os itens do gabarito.

Uso:  .venv/Scripts/python scripts/avaliar_verificacao.py [--reservados] [--sem-llm] [--detalhes]
                                                           [conjunto ...]

Métricas (docs/05 §3.1):
- revocação de erros: erros do gabarito (não atende / divergente) que o sistema apontou;
  "marcado para confirmação" = não verificável ou com baixa confiança (não passou batido);
- falso "atende": erro real classificado como "atende" sem baixa confiança (precisa ser 0);
- falsos alarmes: "não atende"/"divergente" onde o gabarito diz que atende (ou não lista);
- classificação correta: mesmo status do gabarito, entre os itens do gabarito.
O LLM precisa do Ollama ligado; as respostas ficam em cache (dados_privados/cache/llm).
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from arquiteto_auditor.config import pasta_de_dados  # noqa: E402
from arquiteto_auditor.dominio.modelos import StatusItem  # noqa: E402
from arquiteto_auditor.ingestao.leitor import LeitorPDF  # noqa: E402
from arquiteto_auditor.llm.cliente import ClienteLLM  # noqa: E402
from arquiteto_auditor.servicos.analise import DocumentosDoProjeto, analisar  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"
PROBLEMAS = (StatusItem.NAO_ATENDE, StatusItem.DIVERGENTE)


def documentos_do_conjunto(pasta: Path) -> DocumentosDoProjeto:
    def se_existe(nome):
        return pasta / nome if (pasta / nome).exists() else None
    return DocumentosDoProjeto(
        pranchas=sorted(pasta.glob("prancha*.pdf")), memorial=se_existe("memorial.pdf"),
        matricula=se_existe("matricula.pdf"), escritura=se_existe("escritura.pdf"),
        lei_municipal=se_existe("lei_municipal.pdf"),
        norma_condominio=se_existe("norma_condominio.pdf"))


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados = "--reservados" in argumentos
    detalhes, sem_llm = "--detalhes" in argumentos, "--sem-llm" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    cliente = None if sem_llm else ClienteLLM(pasta_cache=pasta_de_dados() / "cache" / "llm")
    if cliente and not cliente.disponivel():
        print("Ollama indisponível: rode com --sem-llm ou ligue o Ollama.")
        return 2
    leitor = LeitorPDF()
    total = Counter()
    falsos_atende, alarmes, inicio = [], [], time.time()
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        resultado = analisar(documentos_do_conjunto(pasta), leitor=leitor, cliente=cliente)
        esperados = {(i["chave"], i.get("escopo")): i["status"]
                     for i in gabarito["itens_esperados"]}
        obtidos = {(i.chave, i.escopo): i for i in resultado.itens}
        total["conjuntos"] += 1
        for chave, esperado in esperados.items():
            item = obtidos.get(chave)
            status = item.status if item else None
            total["itens do gabarito"] += 1
            total["classificação certa"] += status == esperado
            if esperado in PROBLEMAS:
                total["erros no gabarito"] += 1
                if status in PROBLEMAS:
                    total["erros apontados"] += 1
                elif status == StatusItem.NAO_VERIFICAVEL or (item and item.baixa_confianca):
                    total["erros marcados para confirmação"] += 1
                else:
                    falsos_atende.append(f"{pasta.name} {chave}: {status}")
            if detalhes and status != esperado:
                baixa = " (baixa confiança)" if item and item.baixa_confianca else ""
                print(f"  {pasta.name} {chave[0]:22} {chave[1] or '':24} esperado={esperado:16} "
                      f"obtido={status}{baixa}"
                      f" — {item.mensagem[:90] if item else 'item ausente'}")
        for chave, item in obtidos.items():
            if item.status in PROBLEMAS and esperados.get(chave, "atende") not in PROBLEMAS:
                alarmes.append(f"{pasta.name} {chave[0]} {chave[1] or ''}: {item.status}"
                               f"{' (baixa confiança)' if item.baixa_confianca else ''}")
        for item in resultado.itens:
            total["itens gerados"] += 1
            total["itens com evidência"] += bool(item.evidencias) or (
                item.status == StatusItem.NAO_VERIFICAVEL)

    erros = total["erros no gabarito"] or 1
    print(f"\nConjuntos: {total['conjuntos']}")
    apontados, marcados = total["erros apontados"], total["erros marcados para confirmação"]
    print(f"Revocação: {apontados}/{total['erros no gabarito']} apontados "
          f"({100 * apontados / erros:.1f}%) + {marcados} marcados para confirmação "
          f"({100 * (apontados + marcados) / erros:.1f}% no total)")
    print(f"Falso \"atende\" (crítico, meta 0): {len(falsos_atende)} {falsos_atende}")
    print(f"Falsos alarmes: {len(alarmes)} "
          f"({len(alarmes) / max(total['conjuntos'], 1):.2f} por conjunto)")
    for alarme in alarmes:
        print(f"  {alarme}")
    print(f"Classificação certa: {total['classificação certa']}/{total['itens do gabarito']} "
          f"({100 * total['classificação certa'] / max(total['itens do gabarito'], 1):.1f}%)")
    print(f"Itens com evidência (ou não verificáveis): {total['itens com evidência']}/"
          f"{total['itens gerados']}")
    print(f"Tempo: {time.time() - inicio:.0f} s")
    return 1 if falsos_atende else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
