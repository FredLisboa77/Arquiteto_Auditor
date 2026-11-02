"""Testes da leitura dos valores dos parâmetros: tabelas, texto com LLM e extrator (Fase 8).

O LLM é substituído por um "LLM falso" que devolve respostas programadas, inclusive erradas,
para provar que o código rejeita citação inventada, número trocado, outra zona etc.
"""

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from arquiteto_auditor.dominio.documento import (
    DocumentoLido,
    OrigemPalavra,
    PaginaLida,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.dominio.modelos import Evidencia, OrigemValor, TipoDocumento, ValorExtraido
from arquiteto_auditor.extracao.parametros.definicoes import DEFINICOES
from arquiteto_auditor.extracao.parametros.extrator import ParametrosDoDocumento, ler_parametros
from arquiteto_auditor.extracao.parametros.hierarquia import adotar
from arquiteto_auditor.extracao.parametros.tabelas import (
    condicao_atendida,
    ler_tabelas_de_parametros,
    mesma_zona,
)
from arquiteto_auditor.extracao.parametros.texto import ler_texto_de_parametros
from arquiteto_auditor.extracao.parametros.trechos import recortar
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido
from arquiteto_auditor.ingestao.leitor import LeitorPDF
from arquiteto_auditor.ingestao.tabelas import ler_tabelas
from arquiteto_auditor.llm.cliente import LLMIndisponivel


def _corrido(linhas: list[str]) -> TextoCorrido:
    palavras = []
    for i, linha in enumerate(linhas):
        x = 50.0
        for token in linha.split():
            palavras.append(Palavra(texto=token, bbox=(x, 50 + 15 * i, x + 5 * len(token),
                                                       60 + 15 * i),
                                    confianca=1.0, origem=OrigemPalavra.VETORIAL, bloco=1,
                                    linha=i))
            x += 5 * len(token) + 4
    pagina = PaginaLida(numero=1, largura=595, altura=842, tipo=TipoPagina.VETORIAL,
                        palavras=palavras)
    return TextoCorrido(DocumentoLido(arquivo="lei.pdf", hash_sha256="0" * 64,
                                      paginas=[pagina], tipo=TipoDocumento.LEI_MUNICIPAL))


def _tabelas_do_pdf(tmp_path: Path, dados, estilo=()):
    tabela = Table(dados)
    tabela.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, "black"), *estilo]))
    caminho = tmp_path / "lei.pdf"
    SimpleDocTemplate(str(caminho), pagesize=A4).build([tabela])
    documento = LeitorPDF(pasta_cache=tmp_path / "cache", usar_ocr=False).ler(caminho)
    return ler_tabelas(caminho, documento)


def _valores(lidos: dict) -> dict:
    return {chave: [v.valor for v in valores] for chave, valores in lidos.items()}


# ------------------------------------------------------------------ tabelas


def test_mesma_zona():
    assert mesma_zona("ZR-2", "ZR-2") and mesma_zona("ZR 2", "zr-2") and mesma_zona("ZR2", "ZR-2")
    assert not mesma_zona("ZR-20", "ZR-2") and not mesma_zona("ZR-1", "ZR-2")
    assert not mesma_zona("", "ZR-2")


def test_condicao_de_area_do_lote():
    assert condicao_atendida("Lotes com área até 600 m²", 450) is True
    assert condicao_atendida("Lotes com área até 600 m²", 600) is True
    assert condicao_atendida("Lotes com área acima de 600 m²", 600) is False
    assert condicao_atendida("Lotes com área superior a 300 m²", 525) is True
    assert condicao_atendida("Lotes de esquina", 525) is None  # não entendida
    assert condicao_atendida("Parâmetro", 525) is None


def test_tabela_com_uma_linha_por_zona(tmp_path):
    tabelas = _tabelas_do_pdf(tmp_path, [
        ["Zona", "Lote mínimo (m²)", "Recuo frontal mínimo (m)", "Taxa de ocupação máxima (%)"],
        ["ZR-1", "360,00", "6,00", "50"],
        ["ZR-2", "250,00", "5,00", "40"]])
    lidos = ler_tabelas_de_parametros(tabelas, "ZR-2", "lei.pdf")
    assert _valores(lidos) == {"LOTE_AREA_MIN": [250.0], "RECUO_FRONTAL": [5.0],
                               "TO_MAX": [40.0]}
    assert lidos["TO_MAX"][0].evidencias[0].trecho == "ZR-2 | Taxa de ocupação máxima (%) | 40"
    assert lidos["TO_MAX"][0].unidade == "%"


def test_tabela_com_uma_coluna_por_zona(tmp_path):
    tabelas = _tabelas_do_pdf(tmp_path, [
        ["Parâmetro", "ZR-1", "ZR-2", "ZR-3"],
        ["Recuo lateral mínimo (m)", "2,00", "1,50", "1,50"],
        ["Número máximo de pavimentos", "2", "3", "4"]])
    assert _valores(ler_tabelas_de_parametros(tabelas, "ZR-2", "lei.pdf")) == {
        "RECUO_LATERAL_E": [1.5], "RECUO_LATERAL_D": [1.5], "PAVIMENTOS_MAX": [3.0]}


def test_tabela_por_faixa_de_area_do_lote(tmp_path):
    tabelas = _tabelas_do_pdf(tmp_path, [
        ["Zona", "Parâmetro", "Lotes com área até 600 m²", "Lotes com área acima de 600 m²"],
        ["ZR-1", "Recuo frontal mínimo (m)", "4,00", "6,00"],
        ["", "Taxa de ocupação máxima (%)", "40", "45"],
        ["ZR-2", "Recuo frontal mínimo (m)", "5,00", "4,00"],
        ["", "Taxa de ocupação máxima (%)", "50", "55"]],
        estilo=[("SPAN", (0, 1), (0, 2)), ("SPAN", (0, 3), (0, 4))])
    assert _valores(ler_tabelas_de_parametros(tabelas, "ZR-2", "lei.pdf", area_lote=700)) == {
        "RECUO_FRONTAL": [4.0], "TO_MAX": [55.0]}
    lidos = ler_tabelas_de_parametros(tabelas, "ZR-2", "lei.pdf", area_lote=450)
    assert _valores(lidos) == {"RECUO_FRONTAL": [5.0], "TO_MAX": [50.0]}
    assert lidos["TO_MAX"][0].observacao == "Condição: Lotes com área até 600 m²."
    # Sem a área do lote: as duas opções ficam, para o revisor escolher.
    assert _valores(ler_tabelas_de_parametros(tabelas, "ZR-2", "lei.pdf")) == {
        "RECUO_FRONTAL": [5.0, 4.0], "TO_MAX": [50.0, 55.0]}


# ------------------------------------------------------------------ texto (LLM falso)


class _LLMFalso:
    """Devolve a resposta programada para o parâmetro citado no pedido; senão, "nada"."""

    def __init__(self, respostas: dict[str, dict]):
        self.respostas, self.pedidos = respostas, []

    def pedir_json(self, sistema, usuario, esquema):
        self.pedidos.append(usuario)
        for descricao, resposta in self.respostas.items():
            if f"Parâmetro: {descricao}\n" in usuario:
                return resposta
        return {"numero_do_trecho": None, "citacao": None, "valor": None, "unidade": None}


def _resposta(citacao, valor, numero=1):
    return {"numero_do_trecho": numero, "citacao": citacao, "valor": valor, "unidade": None}


LEI = [
    "CAPÍTULO III - DOS PARÂMETROS",
    "Art. 14. Na Zona Residencial 1 (ZR-1), ficam estabelecidos os seguintes",
    "parâmetros: a) recuo frontal mínimo: 6,00 m; b) taxa de ocupação máxima: 45%;",
    "Art. 15. Na Zona Residencial 2 (ZR-2), ficam estabelecidos os seguintes",
    "parâmetros: a) recuo frontal mínimo: 5,00 m; b) taxa de ocupação máxima: 50%;",
    "Art. 22. Na ZR-2, o recuo frontal mínimo será de 5,00 m. (Redação dada pela Lei",
    "nº 282, de 2016) Redação anterior: “Na ZR-2, o recuo frontal mínimo será de 7,00 m.”",
    "ANEXO II - PARÂMETROS URBANÍSTICOS POR ZONA",
    "ES | Recuo frontal mínimo (m) 5,00 4,00",
]


def _ler_texto(linhas, respostas, zona="ZR-2"):
    corrido = _corrido(linhas)
    llm = _LLMFalso(respostas)
    lidos = ler_texto_de_parametros(recortar(corrido), corrido, "lei.pdf", DEFINICOES, zona,
                                    llm)
    return lidos, llm


def test_valor_do_llm_confirmado_pela_citacao():
    lidos, _ = _ler_texto(LEI, {
        "recuo frontal mínimo": _resposta("Na ZR-2, o recuo frontal mínimo será de 5,00 m.",
                                          5.0, numero=2),
        "taxa de ocupação máxima": _resposta("b) taxa de ocupação máxima: 50%;", 50)})
    assert _valores(lidos) == {"RECUO_FRONTAL": [5.0], "TO_MAX": [50.0]}
    valor = lidos["TO_MAX"][0]
    assert valor.origem == "llm" and valor.unidade == "%"
    assert valor.evidencias[0].trecho == "taxa de ocupação máxima: 50%"


@pytest.mark.parametrize("resposta", [
    _resposta("Na ZR-2, o recuo frontal mínimo será de 4,00 m.", 4.0),  # citação inventada
    _resposta("Na ZR-2, o recuo frontal mínimo será de 5,00 m.", 4.0),  # número fora da citação
    _resposta("Na ZR-2, o recuo frontal mínimo será de 7,00 m.", 7.0),  # redação anterior
    _resposta("a) recuo frontal mínimo: 6,00 m;", 6.0),  # outra zona (ZR-1)
    _resposta("b) taxa de ocupação máxima: 50%;", 50),  # outro parâmetro
    _resposta("Recuo frontal mínimo (m) 5,00 4,00", 5.0),  # sem código de zona (tabela no OCR)
])
def test_resposta_errada_do_llm_e_descartada(resposta):
    lidos, _ = _ler_texto(LEI, {"recuo frontal mínimo": resposta})
    assert "RECUO_FRONTAL" not in lidos


def test_llm_so_e_chamado_quando_ha_trecho_do_parametro():
    _, llm = _ler_texto(LEI, {})
    perguntados = {d.descricao for d in DEFINICOES
                   if any(f"Parâmetro: {d.descricao}\n" in p for p in llm.pedidos)}
    assert perguntados == {"recuo frontal mínimo", "taxa de ocupação máxima"}


NORMA = [
    "IV. MUROS E FECHAMENTOS",
    "16. O muro perimetral do condomínio tem altura de 2.50 m e não poderá sofrer alteração.",
    "17.1. Frente do lote: não poderá ser construído muro, admitindo-se gradil de até 1.20 m;",
    "17.2. Fundo do lote: muro de 2.20 m (dois metros e vinte centímetros) de altura;",
    "17.3. Laterais do lote: muro de 80 cm de altura no trecho do recuo frontal, subindo",
    "até a altura de 2.20 m;",
]
MURO = next(d.descricao for d in DEFINICOES if d.nome == "muro_altura_max")


@pytest.mark.parametrize("citacao, valor, aceito", [
    ("17.2. Fundo do lote: muro de 2.20 m (dois metros e vinte centímetros) de altura;", 2.2,
     True),
    ("17.3. Laterais do lote: muro de 80 cm de altura no trecho do recuo frontal, subindo até "
     "a altura de 2.20 m;", 2.2, True),
    ("17.3. Laterais do lote: muro de 80 cm de altura no trecho do recuo frontal", 0.8, False),
    ("16. O muro perimetral do condomínio tem altura de 2.50 m", 2.5, False),
    ("admitindo-se gradil de até 1.20 m;", 1.2, False),
])
def test_excecoes_do_muro(citacao, valor, aceito):
    lidos, _ = _ler_texto(NORMA, {MURO: _resposta(citacao, valor)}, zona=None)
    assert ("MURO_ALTURA_MAX" in lidos) == aceito


# ------------------------------------------------------------------ extrator


def _lei_em_pdf(tmp_path: Path) -> tuple[Path, DocumentoLido]:
    estilo = getSampleStyleSheet()["Normal"]
    caminho = tmp_path / "lei.pdf"
    SimpleDocTemplate(str(caminho), pagesize=A4).build([
        Paragraph("Art. 15. Na Zona Residencial 2 (ZR-2), a taxa de ocupação máxima é de "
                  "50%.", estilo),
        Paragraph("ANEXO I - PERÍMETROS", estilo),
        Paragraph("ZR-2 - Zona Residencial 2: compreende o Residencial Correia.", estilo)])
    return caminho, LeitorPDF(pasta_cache=tmp_path / "cache", usar_ocr=False).ler(caminho)


def test_extrator_sem_zona_nao_le_parametros(tmp_path):
    caminho, documento = _lei_em_pdf(tmp_path)
    llm = _LLMFalso({})
    lido = ler_parametros(caminho, documento, "prefeitura", cliente=llm,
                          nome_condominio="Jardins do Pinto")
    assert lido.zona is None and lido.valores == {} and llm.pedidos == []


def test_extrator_com_e_sem_llm(tmp_path):
    caminho, documento = _lei_em_pdf(tmp_path)
    llm = _LLMFalso({"taxa de ocupação máxima": _resposta(
        "Na Zona Residencial 2 (ZR-2), a taxa de ocupação máxima é de 50%.", 50)})
    lido = ler_parametros(caminho, documento, "prefeitura", cliente=llm,
                          nome_condominio="Residencial Correia")
    assert lido.zona.valor == "ZR-2"
    assert lido.valores["TO_MAX"].valor == 50 and not lido.sem_llm

    sem = ler_parametros(caminho, documento, "prefeitura", cliente=None,
                         nome_condominio="Residencial Correia")
    assert sem.sem_llm and sem.valores == {}

    class _Desligado:
        def pedir_json(self, *args):
            raise LLMIndisponivel("desligado")

    desligado = ler_parametros(caminho, documento, "prefeitura", cliente=_Desligado(),
                               nome_condominio="Residencial Correia")
    assert desligado.sem_llm and desligado.zona.valor == "ZR-2"


# ------------------------------------------------------------------ hierarquia


def _lido(chave, valor, documento):
    return ValorExtraido(campo=chave, valor=valor, origem=OrigemValor.VETORIAL, confianca=0.9,
                         evidencias=[Evidencia(documento=documento, pagina=2,
                                               trecho=f"{chave} = {valor}")])


def _documento(fonte, **valores):
    arquivo = "lei.pdf" if fonte == "prefeitura" else "norma.pdf"
    return ParametrosDoDocumento(arquivo=arquivo, fonte=fonte, valores={
        chave: _lido(chave, valor, arquivo) for chave, valor in valores.items()})


def test_prefeitura_prevalece_sobre_o_condominio():
    adotados = adotar(_documento("prefeitura", TO_MAX=50.0, RECUO_FRONTAL=5.0),
                      _documento("condominio", TO_MAX=35.0, RECUO_FRONTAL=5.0,
                                 MURO_ALTURA_MAX=2.2))
    to = adotados["TO_MAX"]
    assert (to.valor.valor, to.fonte, to.conflito) == (50.0, "prefeitura", True)
    assert to.valor_condominio.valor == 35.0
    assert "define 35" in to.observacao and "norma.pdf, pág. 2" in to.observacao
    assert "prevalece" in to.observacao

    recuo = adotados["RECUO_FRONTAL"]
    assert (recuo.valor.valor, recuo.fonte, recuo.conflito) == (5.0, "prefeitura", False)
    assert recuo.observacao == "A norma do condomínio define o mesmo valor."

    muro = adotados["MURO_ALTURA_MAX"]  # só o condomínio define (e é o normal)
    assert (muro.valor.valor, muro.fonte) == (2.2, "condominio")
    assert muro.valor.status == "automatico"


def test_parametro_da_lei_achado_so_no_condominio_fica_pendente():
    """"Não achei na lei" não é "a lei não define": a leitura da lei pode ter falhado."""
    adotados = adotar(_documento("prefeitura"), _documento("condominio", RECUO_FUNDOS=1.5))
    recuo = adotados["RECUO_FUNDOS"]
    assert (recuo.valor.valor, recuo.fonte) == (1.5, "condominio")
    assert recuo.valor.status == "pendente_confirmacao"
    assert "Confirme se a lei municipal" in recuo.observacao


def test_nada_e_inventado_sem_documentos():
    assert adotar(None, None) == {}
    assert set(adotar(_documento("prefeitura", CA_MAX=1.0), None)) == {"CA_MAX"}
