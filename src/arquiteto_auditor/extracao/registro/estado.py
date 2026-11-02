"""Estado atual do imóvel: os atos da matrícula aplicados em ordem (docs/03 §5.3).

- ÁREA: vem da abertura ("com a área de 300,00 m²") e é trocada a cada retificação (a nova
  descrição: "passa a ser a seguinte: ... área de 312,50 m²").
- PROPRIETÁRIO: o da abertura ("PROPRIETÁRIA: ...") e, depois, o adquirente de cada venda ou
  doação ("..., por venda, a FULANO," ou "ADQUIRENTE: FULANO").
- ÔNUS ATIVOS: alienação fiduciária e hipoteca entram; o cancelamento tira o ato citado
  ("Fica cancelado o registro R-3/...").
Cada campo aponta o ato que o definiu. Fica PENDENTE de confirmação quando: um ato não
compreendido vem depois desse ato (pode ter mudado o campo), o OCR do trecho tem baixa
confiança, ou o número não confere com o extenso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from arquiteto_auditor.config import limiar_confianca_ocr
from arquiteto_auditor.dominio.modelos import OrigemValor, StatusConfirmacao, ValorExtraido
from arquiteto_auditor.dominio.registro import AtoMatricula, TipoAto
from arquiteto_auditor.extracao.registro.comum import AreaLida, NomeLido, ler_area, ler_nome
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido, normalizar

TAMANHO_CABECALHO = 12  # "R-3/15.860": o código do ato, no início do cabeçalho
CONFIANCA = 0.9

_PROPRIETARIO = re.compile(r"PROPRIETARI[OA]S?\s*:\s*")
_ADQUIRENTE = re.compile(r"ADQUIRENTES?\s*:\s*|OUTORGAD[OA]S?\s+COMPRADOR\w*\s*:\s*"
                         r"|POR\s+(?:VENDA|DOACAO)\s*,?\s*(?:AO|A)\s+")
_CITACAO = re.compile(r"\b(?P<letra>R|AV)\s*[-.]?\s*(?P<numero>\d{1,3})\s*/")


@dataclass(frozen=True)
class AtoComPosicao:
    ato: AtoMatricula
    inicio: int  # trecho do ato no texto corrido
    fim: int


def calcular_estado(atos: list[AtoComPosicao], corrido: TextoCorrido, arquivo: str,
                    suspeitos: list[int] = ()) -> tuple[dict[str, ValorExtraido], list[str]]:
    """Estado atual; `suspeitos` = posições de possíveis atos com o código ilegível."""
    texto = corrido.texto
    plano = texto.replace("\n", " ")  # nomes quebrados em duas linhas (mesmo tamanho)
    normalizado = normalizar(plano)
    pendencias: list[str] = []
    # campo → (valor, índice do ato, (início, fim) da evidência, (início, fim) da confiança,
    #          área lida)
    achados: dict[str, tuple] = {}
    onus: dict[str, AtoComPosicao] = {}
    ultimo_onus: AtoComPosicao | None = None

    for indice, item in enumerate(atos):
        ato, inicio, fim = item.ato, item.inicio, item.fim
        if ato.tipo in (TipoAto.ABERTURA, TipoAto.RETIFICACAO):
            busca = inicio
            if ato.tipo == TipoAto.RETIFICACAO:
                seguinte = normalizado.find("SEGUINTE", inicio, fim)
                busca = seguinte if seguinte >= 0 else inicio
            area = ler_area(plano, normalizado, busca, fim)
            if area:
                achados["TERRENO_AREA"] = (area.valor, indice, (area.inicio, area.fim),
                                           (area.inicio_numero, area.fim_numero), area)
            elif ato.tipo == TipoAto.RETIFICACAO:
                pendencias.append(f"Retificação {ato.codigo}: nova área não encontrada.")
        if ato.tipo == TipoAto.ABERTURA:
            m = _PROPRIETARIO.search(normalizado, inicio, fim)
            nome = ler_nome(plano, m.end()) if m else None
            if nome:
                achados["PROPRIETARIO"] = (nome.texto, indice, (m.start(), nome.fim),
                                           (m.end(), nome.fim), nome)
        if ato.tipo in (TipoAto.COMPRA_E_VENDA, TipoAto.DOACAO):
            m = _ADQUIRENTE.search(normalizado, inicio, fim)
            nome = ler_nome(plano, m.end()) if m else None
            if nome:
                achados["PROPRIETARIO"] = (nome.texto, indice, (m.start(), nome.fim),
                                           (m.end(), nome.fim), nome)
            else:
                pendencias.append(f"Ato {ato.codigo}: adquirente não encontrado.")
        if ato.tipo in (TipoAto.ALIENACAO_FIDUCIARIA, TipoAto.HIPOTECA):
            onus[ato.codigo] = item
            ultimo_onus = item
        if ato.tipo == TipoAto.CANCELAMENTO:
            citados = [f"{'R' if c['letra'] == 'R' else 'AV'}-{int(c['numero'])}"
                       for c in _CITACAO.finditer(normalizado, inicio + 8, fim)]
            cancelados = [c for c in citados if c in onus]
            for codigo in cancelados:
                del onus[codigo]
            if not cancelados:
                pendencias.append(f"Cancelamento {ato.codigo}: o ato cancelado "
                                  f"({', '.join(citados) or 'não citado'}) não é um ônus lido.")
            ultimo_onus = item

    # (posição no texto, descrição) de atos que podem ter mudado o estado sem ser entendidos
    nao_compreendidos = [(item.inicio, f"o ato {item.ato.codigo}, posterior, não foi "
                                       "compreendido")
                         for item in atos if item.ato.tipo == TipoAto.OUTRO]
    nao_compreendidos += [(p, "há um possível ato posterior com o código ilegível")
                          for p in suspeitos]

    def montar(campo, valor, indice, trecho, trechos_de_confianca, lido) -> ValorExtraido:
        """Valor do estado atual; a confiança do OCR vem só dos trechos que o definem."""
        evidencia = corrido.evidencia(*trecho, arquivo)
        leituras = [c for a, b in trechos_de_confianca
                    if (c := corrido.confianca(a, b)) is not None]
        ocr = min(leituras) if leituras else None
        evidencia = evidencia.model_copy(update={"confianca_ocr": ocr})
        motivos = [descricao for posicao, descricao in nao_compreendidos
                   if posicao > atos[indice].inicio]
        if ocr is not None and ocr < limiar_confianca_ocr():
            motivos.append(f"leitura (OCR) com baixa confiança ({ocr:.2f})")
        if isinstance(lido, NomeLido) and lido.limpo:
            motivos.append("sinais soltos do OCR removidos do nome")
        divergente = isinstance(lido, AreaLida) and lido.extenso is not None
        if divergente and lido.extenso != int(lido.valor):
            motivos.append(f"o número não confere com o extenso ({lido.extenso} m²)")
        escaneado = corrido.confianca(*trecho) is not None
        origem = atos[indice]
        return ValorExtraido(
            campo=campo, valor=valor, unidade="m2" if campo == "TERRENO_AREA" else None,
            origem=OrigemValor.OCR if escaneado else OrigemValor.VETORIAL,
            confianca=round(CONFIANCA * (ocr if ocr is not None else 1.0), 3),
            evidencias=[evidencia], ato_origem=origem.ato.codigo,
            status=StatusConfirmacao.PENDENTE if motivos else StatusConfirmacao.AUTOMATICO,
            observacao=("Confirme: " + "; ".join(motivos) + ".") if motivos else None)

    def cabecalho(item: AtoComPosicao) -> tuple[int, int]:
        return item.inicio, min(item.fim, item.inicio + TAMANHO_CABECALHO)

    estado: dict[str, ValorExtraido] = {}
    for campo, (valor, indice, trecho, confianca, lido) in achados.items():
        estado[campo] = montar(campo, valor, indice, trecho, [confianca], lido)
    if atos:
        # ônus: a leitura que importa é a do código de cada ato envolvido
        envolvidos = list(onus.values()) + ([ultimo_onus] if ultimo_onus else [])
        origem = max(onus.values(), key=lambda i: i.inicio) if onus else (ultimo_onus or atos[0])
        estado["ONUS_ATIVOS"] = montar(
            "ONUS_ATIVOS", ", ".join(onus) or "nenhum", atos.index(origem),
            (origem.inicio, min(origem.fim, origem.inicio + 300)),
            [cabecalho(item) for item in envolvidos], None)
    return estado, pendencias
