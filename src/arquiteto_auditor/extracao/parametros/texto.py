"""Parâmetros escritos em texto corrido (artigos, itens), lidos pelo LLM com citação.

Para cada parâmetro:
1. o código escolhe os trechos que citam o parâmetro (sinônimos) e, na lei, a zona;
   nenhum trecho → o LLM nem é chamado (não há o que inventar);
2. o LLM recebe só esses trechos e devolve {numero_do_trecho, citacao, valor, unidade};
3. o código confere (qualquer falha → o valor é descartado):
   - a citação existe num dos trechos enviados (llm/citacao.py);
   - o número está na citação e é relido dela pelo normalizador;
   - a parte da frase onde está o número cita o parâmetro e não fala de exceção
     (muro perimetral, lote de esquina...), nem de redação anterior/revogada;
   - a unidade combina com a do parâmetro;
   - na lei, o último código de zona antes do número (ou o do título) é a zona do lote.
"""

from __future__ import annotations

import re

from arquiteto_auditor.dominio.modelos import OrigemValor, ValorExtraido
from arquiteto_auditor.extracao.parametros.definicoes import DefinicaoParametro
from arquiteto_auditor.extracao.parametros.tabelas import mesma_zona
from arquiteto_auditor.extracao.parametros.trechos import Trecho
from arquiteto_auditor.extracao.parametros.zona import ultimo_codigo
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido, normalizar
from arquiteto_auditor.llm import carregar_prompt
from arquiteto_auditor.llm.citacao import localizar_citacao, reler_valor
from arquiteto_auditor.llm.cliente import ClienteLLM, RespostaInvalida

MAXIMO_TRECHOS = 5
CONFIANCA_LLM = 0.8
ZONA_DA_NORMA = "(regulamento do condomínio: vale para todos os lotes, não há zona)"

ESQUEMA = {
    "type": "object",
    "properties": {
        "numero_do_trecho": {"type": ["integer", "null"]},
        "citacao": {"type": ["string", "null"]},
        "valor": {"type": ["number", "null"]},
        "unidade": {"type": ["string", "null"]},
    },
    "required": ["numero_do_trecho", "citacao", "valor", "unidade"],
}

# Onde uma "parte da frase" começa ou termina: ";", fim de frase, alínea "b)", inciso "II -".
_LIMITE_DE_CLAUSULA = re.compile(
    r";|\.\s+(?=[A-ZÀ-Ú\"“(])|\s[a-z]\)\s|\s[IVX]{1,4}\s+-\s")
_REVOGADO = re.compile(r"REDACAO ANTERIOR|REVOGAD|REDACAO ORIGINAL")


def _padrao_zona(zona: str) -> re.Pattern:
    partes = re.findall(r"[A-Z]+|\d+", normalizar(zona))
    return re.compile(r"(?<![A-Z0-9])" + r"\s*-?\s*".join(partes) + r"(?![A-Z0-9])")


def selecionar_trechos(trechos: list[Trecho], definicao: DefinicaoParametro,
                       zona: str | None, exigir_zona: bool = True) -> list[Trecho]:
    """Trechos que citam o parâmetro (e a zona, na lei), os mais específicos primeiro.

    exigir_zona=False só no teste de alucinação: manda ao LLM trechos de outras zonas.
    """
    padrao = _padrao_zona(zona) if zona and exigir_zona else None
    escolhidos = []
    for ordem, trecho in enumerate(trechos):
        if not definicao.citado_em(trecho.texto):
            continue
        if padrao is not None:
            no_texto = bool(padrao.search(normalizar(trecho.texto)))
            if not (no_texto or padrao.search(normalizar(trecho.titulo))):
                continue
            nota = 0 if no_texto else 1
        else:
            nota = 0
        escolhidos.append((nota, len(trecho.texto) > 600, ordem, trecho))
    escolhidos.sort(key=lambda item: item[:3])
    return [item[3] for item in escolhidos[:MAXIMO_TRECHOS]]


def clausulas(texto: str) -> list[str]:
    """O texto dividido nas partes da frase (os separadores ficam de fora)."""
    return [parte for parte in _LIMITE_DE_CLAUSULA.split(texto) if parte.strip()]


def limites_da_clausula(texto: str, inicio: int, fim: int) -> tuple[int, int]:
    """Onde começa e termina a parte da frase em volta das posições [inicio, fim)."""
    antes = [m.end() for m in _LIMITE_DE_CLAUSULA.finditer(texto, 0, inicio)]
    depois = _LIMITE_DE_CLAUSULA.search(texto, fim)
    a, b = (antes[-1] if antes else 0), (depois.start() if depois else len(texto))
    while a < b and texto[a].isspace():
        a += 1
    return a, b


def _clausula(texto: str, inicio: int, fim: int) -> str:
    return texto[slice(*limites_da_clausula(texto, inicio, fim))]


_UNIDADES_ACEITAS = {"m": {"m"}, "m2": {"m2"}, "%": {"%"}, "pavimentos": {"pavimentos"},
                     None: set()}


def _conferir(resposta: dict, enviados: list[Trecho], corrido: TextoCorrido,
              definicao: DefinicaoParametro, zona: str | None) -> tuple[int, int] | None:
    """Posição (no texto corrido) do número confirmado, ou None se algo não confere."""
    citacao, valor = resposta.get("citacao"), resposta.get("valor")
    numero = resposta.get("numero_do_trecho")
    ordem = list(enviados)
    if isinstance(numero, int) and 1 <= numero <= len(enviados):
        ordem.insert(0, ordem.pop(numero - 1))  # primeiro o trecho que o LLM indicou
    for trecho in ordem:
        fonte = corrido.texto[trecho.inicio:trecho.fim]
        posicao = localizar_citacao(citacao, fonte)
        if posicao is None:
            continue
        lido = reler_valor(fonte[posicao[0]:posicao[1]], valor)
        if lido is None:
            return None
        inicio, fim = posicao[0] + lido.inicio, posicao[0] + lido.fim
        clausula = _clausula(fonte, inicio, fim)
        if not definicao.citado_em(clausula) or definicao.tem_excecao(clausula):
            return None
        if definicao.tem_excecao_apos_o_numero(fonte[fim:]):
            return None
        if _REVOGADO.search(normalizar(fonte[max(0, inicio - 120):inicio])):
            return None
        if lido.unidade is not None and lido.unidade not in _UNIDADES_ACEITAS[definicao.unidade]:
            return None
        if zona is not None:
            # O código de zona mais próximo antes do número (ou o do título) precisa ser o da
            # zona do lote; sem código nenhum (ex.: tabela escaneada com a zona ilegível), não
            # há como saber de que zona é o número.
            codigo = ultimo_codigo(fonte[:inicio]) or ultimo_codigo(trecho.titulo)
            if codigo is None or not mesma_zona(codigo.group(1), zona):
                return None
        return trecho.inicio + inicio, trecho.inicio + fim
    return None


def ler_texto_de_parametros(trechos: list[Trecho], corrido: TextoCorrido, arquivo: str,
                            definicoes: tuple[DefinicaoParametro, ...], zona: str | None,
                            cliente: ClienteLLM,
                            exigir_zona: bool = True) -> dict[str, list[ValorExtraido]]:
    """Valores confirmados no texto corrido, por chave do catálogo.

    zona=None → norma do condomínio (sem zona). LLMIndisponivel não é tratado aqui: quem
    chama decide o modo sem LLM.
    """
    sistema = carregar_prompt("parametro_sistema")
    modelo_pedido = carregar_prompt("parametro_pedido")
    resultado: dict[str, list[ValorExtraido]] = {}
    for definicao in definicoes:
        enviados = selecionar_trechos(trechos, definicao, zona, exigir_zona)
        if not enviados:
            continue
        lista = "\n".join(f"[{i}] {t.texto}" for i, t in enumerate(enviados, start=1))
        pedido = (modelo_pedido.replace("<<PARAMETRO>>", definicao.descricao)
                  .replace("<<ZONA>>", zona or ZONA_DA_NORMA)
                  .replace("<<TRECHOS>>", lista))
        try:
            resposta = cliente.pedir_json(sistema, pedido, ESQUEMA)
        except RespostaInvalida:
            continue
        posicao = _conferir(resposta, enviados, corrido, definicao, zona)
        if posicao is None:
            continue
        lido = reler_valor(corrido.texto[posicao[0]:posicao[1]], resposta["valor"])
        trecho = next(t for t in enviados if t.inicio <= posicao[0] < t.fim)
        a, b = limites_da_clausula(corrido.texto[trecho.inicio:trecho.fim],
                                   posicao[0] - trecho.inicio, posicao[1] - trecho.inicio)
        evidencia = corrido.evidencia(trecho.inicio + a, trecho.inicio + b, arquivo)
        # A confiança do OCR que importa é a da palavra do número (a frase e o extenso entre
        # parênteses podem ter um sinal mal lido).
        confianca = corrido.confianca(posicao[0], posicao[0] + 1)
        evidencia = evidencia.model_copy(update={"confianca_ocr": confianca})
        for chave in definicao.chaves:
            resultado.setdefault(chave, []).append(ValorExtraido(
                campo=chave, valor=lido.valor, unidade=definicao.unidade,
                origem=OrigemValor.LLM, confianca=CONFIANCA_LLM, evidencias=[evidencia]))
    return resultado
