"""Teste de alucinação (Fase 8): com o parâmetro APAGADO do documento, nada pode ser achado.

Uso:  .venv/Scripts/python scripts/avaliar_alucinacao.py [--reservados] [--detalhes] [conjunto ...]

Para cada conjunto, documento (lei e norma) e parâmetro:
- as tabelas são retiradas e, nos trechos da zona do lote (todos, na norma), as partes da
  frase que citam o parâmetro são apagadas. Os valores de OUTRAS zonas continuam lá, como
  isca ("Na ZR-1, a taxa de ocupação máxima é de 45%" quando a zona é a ZR-2);
- modo NORMAL: a leitura de sempre (o LLM só é chamado se sobrou trecho do parâmetro na zona);
- modo FORÇADO: o LLM recebe os trechos do parâmetro de qualquer zona e precisa responder
  que não há valor para a zona do lote — ou o código precisa rejeitar a resposta.
Resultado esperado: zero valores inventados nos dois modos.
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
from arquiteto_auditor.dominio.documento import (  # noqa: E402
    DocumentoLido,
    OrigemPalavra,
    PaginaLida,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.extracao.parametros.definicoes import DEFINICOES  # noqa: E402
from arquiteto_auditor.extracao.parametros.tabelas import mesma_zona  # noqa: E402
from arquiteto_auditor.extracao.parametros.texto import (  # noqa: E402
    clausulas,
    ler_texto_de_parametros,
    selecionar_trechos,
)
from arquiteto_auditor.extracao.parametros.trechos import recortar  # noqa: E402
from arquiteto_auditor.extracao.parametros.zona import ultimo_codigo  # noqa: E402
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido  # noqa: E402
from arquiteto_auditor.ingestao.leitor import LeitorPDF  # noqa: E402
from arquiteto_auditor.ingestao.tabelas import ler_tabelas  # noqa: E402
from arquiteto_auditor.llm.cliente import ClienteLLM  # noqa: E402

PASTA = RAIZ / "dados_sinteticos" / "projetos"


class _Gravador:
    """Passa as perguntas ao cliente de verdade e guarda as respostas (para o relatório)."""

    def __init__(self, cliente: ClienteLLM):
        self.cliente, self.respostas = cliente, []

    def pedir_json(self, sistema, usuario, esquema):
        resposta = self.cliente.pedir_json(sistema, usuario, esquema)
        self.respostas.append(resposta)
        return resposta


def _documento_de_linhas(linhas: list[str], arquivo: str) -> TextoCorrido:
    """Documento sintético de uma página com as linhas dadas (só o texto importa aqui)."""
    palavras = []
    for i, linha in enumerate(linhas):
        x = 0.0
        for token in linha.split():
            palavras.append(Palavra(texto=token, bbox=(x, float(i), x + 1, i + 0.8),
                                    confianca=1.0, origem=OrigemPalavra.VETORIAL, bloco=1,
                                    linha=i))
            x += 2
    pagina = PaginaLida(numero=1, largura=10_000, altura=len(linhas) + 1,
                        tipo=TipoPagina.VETORIAL, palavras=palavras)
    return TextoCorrido(DocumentoLido(arquivo=arquivo, hash_sha256="0" * 64, paginas=[pagina]))


def _da_zona(texto: str, titulo: str, zona: str | None) -> bool:
    if zona is None:
        return True
    codigo = ultimo_codigo(texto) or ultimo_codigo(titulo)
    return codigo is not None and mesma_zona(codigo.group(1), zona)


def apagar_parametro(trechos, definicao, zona: str | None) -> list[str]:
    """Linhas do documento sem as frases do parâmetro na zona do lote (sem as tabelas)."""
    linhas = []
    for trecho in trechos:
        texto = trecho.texto
        if _da_zona(texto, trecho.titulo, zona) and definicao.citado_em(texto):
            texto = "; ".join(p.strip() for p in clausulas(texto)
                              if not definicao.citado_em(p))
        if texto.strip():
            linhas.append(texto)
    return linhas


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    reservados, detalhes = "--reservados" in argumentos, "--detalhes" in argumentos
    nomes = [a for a in argumentos if not a.startswith("--")]
    cliente = ClienteLLM(pasta_cache=pasta_de_dados() / "cache" / "llm")
    if not cliente.disponivel():
        print("Ollama indisponível: ligue o Ollama para este teste.")
        return 2
    leitor = LeitorPDF()
    contagem = {"normal": Counter(), "forçado": Counter()}
    inventados, inicio = [], time.time()
    for pasta in sorted(p for p in PASTA.iterdir() if p.is_dir()):
        gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
        if nomes and pasta.name not in nomes:
            continue
        if not nomes and gabarito.get("reservado_avaliacao", False) != reservados:
            continue
        for arquivo, zona in (("lei_municipal.pdf", gabarito["zona"]),
                              ("norma_condominio.pdf", None)):
            caminho = pasta / arquivo
            documento = leitor.ler(caminho)
            trechos = recortar(TextoCorrido(documento), ler_tabelas(caminho, documento))
            for definicao in DEFINICOES:
                corrido = _documento_de_linhas(apagar_parametro(trechos, definicao, zona),
                                               arquivo)
                restantes = recortar(corrido)
                for modo, exigir_zona in (("normal", True), ("forçado", False)):
                    if not selecionar_trechos(restantes, definicao, zona, exigir_zona):
                        contagem[modo]["sem trecho: LLM não chamado"] += 1
                        continue
                    gravador = _Gravador(cliente)
                    lidos = ler_texto_de_parametros(restantes, corrido, arquivo, (definicao,),
                                                    zona, gravador, exigir_zona)
                    disse_valor = any(r.get("valor") is not None for r in gravador.respostas)
                    if lidos:
                        contagem[modo]["INVENTADO"] += 1
                        valor = next(iter(lidos.values()))[0]
                        inventados.append(f"{pasta.name} {arquivo} {definicao.nome} ({modo}): "
                                          f"{valor.valor} — {valor.evidencias[0].trecho[:80]}")
                    elif disse_valor:
                        contagem[modo]["LLM deu valor, código rejeitou"] += 1
                    else:
                        contagem[modo]["LLM respondeu 'não há'"] += 1
                    if detalhes and disse_valor:
                        resposta = gravador.respostas[-1]
                        print(f"  {pasta.name} {arquivo:20} {definicao.nome:20} {modo:8} "
                              f"LLM: {resposta.get('valor')} — "
                              f"{str(resposta.get('citacao'))[:70]}")

    for modo, c in contagem.items():
        print(f"{modo:8}: {dict(c)}")
    print(f"Valores inventados: {len(inventados)}")
    for linha in inventados:
        print(f"  {linha}")
    print(f"Chamadas ao LLM fora do cache: {cliente.chamadas}")
    print(f"Tempo: {time.time() - inicio:.0f} s")
    return 1 if inventados else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
