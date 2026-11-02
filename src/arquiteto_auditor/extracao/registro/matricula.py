"""Leitura da matrícula (certidão de inteiro teor): atos e estado atual do imóvel (Fase 7).

Convenções do registro de imóveis usadas (Lei 6.015/1973; iguais em todo o país):
- a ABERTURA descreve o imóvel ("IMÓVEL: ...") e o primeiro proprietário;
- cada ato começa numa linha nova com o código "R-n/matrícula" (registro) ou
  "AV-n/matrícula" (averbação), e a numeração é SEQUENCIAL (R-1, AV-2, R-3...);
- o mesmo código aparece no meio do texto quando um ato cita outro ("Fica cancelado o
  registro R-3/12.345"): isso não é ato novo. Por isso só vale como cabeçalho um código no
  início da linha com o número esperado (ou pouco à frente, se um ato ficou ilegível — o
  salto vira pendência); número menor que o esperado é sempre citação;
- o fim dos atos é o fecho da certidão ("CERTIDÃO", "Certifico...").
O tipo de cada ato sai do título antes dos dois-pontos ("COMPRA E VENDA:"); sem título, ou
com o título ilegível, de palavras-chave do corpo (com confiança menor no 2º caso). Ato que
não se encaixa em nenhum tipo vira pendência.
"""

from __future__ import annotations

import re
import unicodedata

from arquiteto_auditor.dominio.datas import encontrar_data
from arquiteto_auditor.dominio.documento import DocumentoLido
from arquiteto_auditor.dominio.registro import AtoMatricula, MatriculaLida, TipoAto
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido

SALTO_MAXIMO = 3  # atos ilegíveis tolerados entre dois cabeçalhos
CONFIANCA_ATO = 0.95  # leitura por regra; multiplicada pela confiança do OCR do cabeçalho
FATOR_SO_PELO_CORPO = 0.8  # o título existe mas não foi reconhecido: tipo pelo corpo do texto

# Tolerante a sujeiras comuns do OCR no cabeçalho: "A V-3", "R-=3", "R-I/..." (I no lugar de 1)
_CABECALHO = re.compile(
    r"^\W{0,3}(?P<letra>R|A\s?V)\s*[-.–=_]{0,3}\s*(?P<numero>[\dIl|O]{1,3})\s*[/-]",
    re.MULTILINE)
_PARECIDOS_COM_DIGITO = str.maketrans("Il|O", "1110")
_NUMERO_MATRICULA = re.compile(r"MATRICULA\s*N[º°O.]?\s*(?P<numero>\d[\d.]*\d)")
_FECHO = re.compile(r"^\W{0,3}CERTID[AÃ]O\b|CERTIFICO", re.MULTILINE)
_TITULO = re.compile(r"^[\W\d]*(?P<titulo>[A-Z][A-Z ,/]{3,60}):")

# (tipo, expressões) em ordem de prioridade, sobre o texto em maiúsculas e sem acentos
_PALAVRAS_CHAVE: list[tuple[TipoAto, tuple[str, ...]]] = [
    (TipoAto.CANCELAMENTO, (r"CANCELA", r"\bBAIXA\b")),
    # "passa a ser a seguinte" / "passando a ter a seguinte descrição": nova descrição do imóvel
    (TipoAto.RETIFICACAO, (r"RETIFICA", r"PASSA\w*\s+A\s+(SER|TER)\s+A\s+SEGUINTE")),
    (TipoAto.ALIENACAO_FIDUCIARIA, (r"ALIEN\w*\s+FIDUCI",)),
    (TipoAto.HIPOTECA, (r"HIPOTEC",)),
    (TipoAto.DOACAO, (r"\bDOACAO\b", r"\bDOOU\b")),
    (TipoAto.COMPRA_E_VENDA, (r"COMPRA\s+E\s+VENDA", r"\bVENDA\b", r"TRANSMIT")),
    (TipoAto.ALTERACAO_DENOMINACAO, (r"DENOMINA", r"NUMERACAO", r"EMPLACAMENTO")),
    (TipoAto.CONSTRUCAO, (r"CONSTRU",)),
]


def _normalizar(texto: str) -> str:
    """Maiúsculas sem acentos, com o MESMO tamanho (as posições continuam valendo)."""
    return "".join(unicodedata.normalize("NFD", c)[0] for c in texto.upper())


def _classificar(texto: str) -> tuple[TipoAto, float]:
    """(tipo, fator de confiança): pelo título; se ele não for reconhecido, pelo corpo."""
    def por_palavras(trecho: str) -> TipoAto | None:
        for tipo, expressoes in _PALAVRAS_CHAVE:
            if any(re.search(e, trecho) for e in expressoes):
                return tipo
        return None

    titulo = _TITULO.match(texto)
    if titulo and (tipo := por_palavras(titulo["titulo"])):
        return tipo, 1.0
    pelo_corpo = por_palavras(texto)
    if pelo_corpo is None:
        return TipoAto.OUTRO, 1.0
    return pelo_corpo, FATOR_SO_PELO_CORPO if titulo else 1.0


def _cabecalhos(normalizado: str, pendencias: list[str]) -> list[tuple[str, int]]:
    """(código, posição) dos cabeçalhos de ato, em ordem; saltos viram pendência."""
    achados, esperado = [], 1
    for m in _CABECALHO.finditer(normalizado):
        numero = int(m["numero"].translate(_PARECIDOS_COM_DIGITO))
        if numero < esperado or numero > esperado + SALTO_MAXIMO:
            continue  # citação de ato anterior (ou número absurdo)
        if numero > esperado:
            faltam = ", ".join(str(n) for n in range(esperado, numero))
            pendencias.append(f"Ato(s) nº {faltam} não encontrado(s) entre os atos lidos "
                              "(página ilegível ou fora da certidão?).")
        letra = "R" if m["letra"] == "R" else "AV"
        achados.append((f"{letra}-{numero}", m.start()))
        esperado = numero + 1
    return achados


def ler_matricula(documento: DocumentoLido) -> MatriculaLida:
    corrido = TextoCorrido(documento)
    texto = corrido.texto
    normalizado = _normalizar(texto)
    pendencias: list[str] = []
    numero = _NUMERO_MATRICULA.search(normalizado)
    cabecalhos = _cabecalhos(normalizado, pendencias)

    inicio_atos = cabecalhos[0][1] if cabecalhos else len(texto)
    fecho = _FECHO.search(normalizado, inicio_atos)
    fim_atos = fecho.start() if fecho else len(texto)
    imovel = normalizado.find("IMOVEL")
    inicio_abertura = imovel if 0 <= imovel < inicio_atos else 0

    trechos = [("ABERTURA", inicio_abertura, inicio_atos)] if inicio_atos > inicio_abertura \
        else []
    for i, (codigo, inicio) in enumerate(cabecalhos):
        fim = cabecalhos[i + 1][1] if i + 1 < len(cabecalhos) else fim_atos
        trechos.append((codigo, inicio, max(fim, inicio)))

    atos = []
    for codigo, inicio, fim in trechos:
        conteudo = texto[inicio:fim].strip()
        if not conteudo:
            continue
        fator = 1.0
        if codigo == "ABERTURA":
            tipo, data = TipoAto.ABERTURA, None
        else:
            corpo = normalizado[inicio:fim]
            achado = encontrar_data(texto[inicio:min(fim, inicio + 120)])
            data = achado[0] if achado else None
            depois_da_data = corpo[achado[2]:] if achado else corpo
            tipo, fator = _classificar(depois_da_data.lstrip(" .-–"))
            if tipo == TipoAto.OUTRO:
                pendencias.append(f"Ato {codigo} não compreendido: confira se ele muda a área, "
                                  "o proprietário ou os ônus do imóvel.")
        confianca_ocr = corrido.confianca(inicio, min(fim, inicio + 120))
        atos.append(AtoMatricula(
            codigo=codigo, tipo=tipo, data=data, texto=conteudo,
            evidencia=corrido.evidencia(inicio, min(fim, inicio + 300), documento.arquivo),
            confianca=round(CONFIANCA_ATO * fator * (confianca_ocr or 1.0), 3)))
    return MatriculaLida(arquivo=documento.arquivo, numero=numero["numero"] if numero else None,
                         atos=atos, pendencias=pendencias)
