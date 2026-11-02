"""Testes da leitura de parâmetros da lei e da norma do condomínio (Fase 8)."""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from arquiteto_auditor.dominio.documento import (
    DocumentoLido,
    OrigemPalavra,
    PaginaLida,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.dominio.modelos import StatusConfirmacao, TipoDocumento
from arquiteto_auditor.extracao.parametros.trechos import recortar, tipo_da_linha
from arquiteto_auditor.extracao.parametros.zona import identificar_zona
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido
from arquiteto_auditor.ingestao.leitor import LeitorPDF
from arquiteto_auditor.ingestao.tabelas import juntar_linhas_da_celula, ler_tabelas


def _pagina(linhas: list[str], numero=1, origem=OrigemPalavra.VETORIAL,
            confianca=1.0) -> PaginaLida:
    palavras = []
    for i, linha in enumerate(linhas):
        x = 50.0
        for token in linha.split():
            palavras.append(Palavra(texto=token, bbox=(x, 50 + 15 * i, x + 5 * len(token),
                                                       60 + 15 * i),
                                    confianca=confianca, origem=origem, bloco=1, linha=i))
            x += 5 * len(token) + 4
    tipo = TipoPagina.ESCANEADA if origem == OrigemPalavra.OCR else TipoPagina.VETORIAL
    return PaginaLida(numero=numero, largura=595, altura=842, tipo=tipo, palavras=palavras)


def _corrido(*paginas) -> TextoCorrido:
    return TextoCorrido(DocumentoLido(arquivo="lei.pdf", hash_sha256="0" * 64,
                                      paginas=list(paginas), tipo=TipoDocumento.LEI_MUNICIPAL))


# ------------------------------------------------------------------ trechos


def test_tipo_da_linha():
    assert tipo_da_linha("Art. 5º Os parâmetros urbanísticos") == "artigo"
    assert tipo_da_linha("Art 12. Na ZR-2") == "artigo"
    assert tipo_da_linha("13.1. Recuo Frontal: mínimo de 3.00 m") == "item"
    assert tipo_da_linha("4, O projeto deverá conter plantas") == "item"  # vírgula do OCR
    assert tipo_da_linha("CAPÍTULO III - DOS PARÂMETROS") == "titulo"
    assert tipo_da_linha("Seção - Zona Residencial 2 (ZR-2)") == "titulo"
    assert tipo_da_linha("IV. MUROS E FECHAMENTOS") == "titulo"
    assert tipo_da_linha("Il. APROVAÇÃO DE PROJETOS") == "titulo"  # "III" lido pelo OCR
    assert tipo_da_linha("a) lote mínimo: 300,00 m²;") == "continuacao"
    assert tipo_da_linha("1.000 (mil) litros.") == "continuacao"
    assert tipo_da_linha("24 meses, contados da aprovação") == "continuacao"


def test_recorte_em_artigos_com_titulo_e_sem_rodape():
    corrido = _corrido(
        _pagina(["LEI 100/2020 - Uso do Solo - página 1",
                 "CAPÍTULO III - DOS PARÂMETROS",
                 "Art. 15. Na Zona Residencial 2 (ZR-2), ficam estabelecidos os seguintes",
                 "parâmetros:",
                 "a) lote mínimo: 300,00 m²;"], numero=1),
        _pagina(["LEI 100/2020 - Uso do Solo - página 2",
                 "b) testada mínima: 8,00 m;",
                 "Art. 16. Na ZR-2, o recuo frontal mínimo será de 5,00 m."], numero=2))
    trechos = recortar(corrido)
    textos = [t.texto for t in trechos]
    assert textos == [
        "CAPÍTULO III - DOS PARÂMETROS",
        "Art. 15. Na Zona Residencial 2 (ZR-2), ficam estabelecidos os seguintes parâmetros: "
        "a) lote mínimo: 300,00 m²; b) testada mínima: 8,00 m;",
        "Art. 16. Na ZR-2, o recuo frontal mínimo será de 5,00 m."]
    assert trechos[1].titulo == "CAPÍTULO III - DOS PARÂMETROS"
    assert (trechos[1].pagina, trechos[2].pagina) == (1, 2)
    assert corrido.texto[trechos[2].inicio:trechos[2].fim] == textos[2]


def test_artigos_parecidos_nao_viram_cabecalho():
    """Artigos que só mudam nos números, no topo de 2 de 4 páginas, continuam no texto."""
    topos = ["Art. 20. Na ZR-1, o nível de ruído máximo é de 55 dB(A).",
             "Art. 21. Na ZR-2, o nível de ruído máximo é de 50 dB(A).", "Texto.", "Texto."]
    corrido = _corrido(*[_pagina([f"LEI 100 - página {n}", topo, f"Art. {30 + n}. Fim."],
                                 numero=n) for n, topo in enumerate(topos, start=1)])
    textos = [t.texto for t in recortar(corrido)]
    assert any("ZR-1" in t for t in textos) and any("ZR-2" in t for t in textos)
    assert not any("LEI 100" in t for t in textos)


def test_trecho_longo_e_dividido():
    linhas = ["Art. 1º Texto inicial."] + [f"continuação número {i} " + "palavra " * 10
                                           for i in range(40)]
    trechos = recortar(_corrido(_pagina(linhas)))
    assert len(trechos) > 1
    assert all(len(t.texto) <= 1500 for t in trechos)


# ------------------------------------------------------------------ zona


ANEXO_I = [
    "ANEXO I - DESCRIÇÃO DOS PERÍMETROS DAS ZONAS",
    "ZR-1 - Zona Residencial 1: compreende as áreas dos seguintes loteamentos",
    "e condomínios: Loteamento Guerra, Jardim Santos, e as áreas contíguas.",
    "ZR-2 - Zona Residencial 2: compreende as áreas dos seguintes loteamentos",
    "e condomínios: Loteamento Fogaça, Parque Nascimento,",
    "Residencial Correia, Vila Nascimento, e as áreas contíguas.",
    "ZM - Zona Mista: compreende as áreas dos seguintes loteamentos e",
    "condomínios: Jardim Barros, Jardim Cunha.",
]


def _zona(linhas, nome, **kw):
    corrido = _corrido(_pagina(linhas, **kw))
    return identificar_zona(recortar(corrido), corrido, nome, "lei.pdf")


def test_zona_pelo_nome_do_condominio():
    zona = _zona(ANEXO_I, "Residencial Correia")
    assert zona.valor == "ZR-2"
    assert zona.status == StatusConfirmacao.AUTOMATICO
    assert zona.evidencias[0].trecho.startswith("ZR-2 - Zona Residencial 2")
    assert zona.evidencias[0].trecho.endswith("Residencial Correia")


def test_zona_sem_o_prefixo_condominio():
    linhas = ANEXO_I[:3] + ["ZR-3 - Zona Residencial 3: compreende Ferreira e Vila Rica."]
    assert _zona(linhas, "Condomínio Ferreira").valor == "ZR-3"


def test_zona_nunca_presumida():
    assert _zona(ANEXO_I, "Jardins do Pinto") is None  # nome não citado: perguntar
    assert _zona(ANEXO_I, None) is None
    assert _zona(["O Residencial Correia fica no Município."], "Residencial Correia") is None


def test_zona_ambigua_fica_pendente():
    linhas = ANEXO_I + ["ZEIS - Zona Especial: Residencial Correia (gleba B)."]
    zona = _zona(linhas, "Residencial Correia")
    assert zona.status == StatusConfirmacao.PENDENTE
    assert "ZEIS" in zona.observacao


def test_zona_lida_por_ocr_fraco_fica_pendente():
    zona = _zona(ANEXO_I, "Residencial Correia", origem=OrigemPalavra.OCR, confianca=0.3)
    assert zona.valor == "ZR-2"
    assert zona.status == StatusConfirmacao.PENDENTE


# ------------------------------------------------------------------ tabelas


def test_juntar_numero_quebrado_na_celula():
    def p(texto, y):
        return Palavra(texto=texto, bbox=(0, y, 20, y + 8), confianca=1.0,
                       origem=OrigemPalavra.VETORIAL)
    assert juntar_linhas_da_celula([p("360,0", 0), p("0", 10)]) == "360,00"
    assert juntar_linhas_da_celula([p("1.000,", 0), p("00", 10)]) == "1.000,00"
    assert juntar_linhas_da_celula([p("Recuo", 0), p("frontal", 10)]) == "Recuo frontal"


def test_tabela_com_celula_mesclada(tmp_path: Path):
    dados = [["Zona", "Parâmetro", "Até 600 m²", "Acima de 600 m²"],
             ["ZR-1", "Lote mínimo (m²)", "300,00", "450,00"],
             ["", "Recuo frontal (m)", "4,00", "6,00"],
             ["ZR-2", "Lote mínimo (m²)", "250,00", "360,00"],
             ["", "Recuo frontal (m)", "5,00", "4,00"]]
    tabela = Table(dados)
    tabela.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, "black"),
                                ("SPAN", (0, 1), (0, 2)), ("SPAN", (0, 3), (0, 4))]))
    caminho = tmp_path / "lei.pdf"
    SimpleDocTemplate(str(caminho), pagesize=A4).build([tabela])

    documento = LeitorPDF(pasta_cache=tmp_path / "cache", usar_ocr=False).ler(caminho)
    [lida] = ler_tabelas(caminho, documento)
    assert (lida.linhas, lida.colunas) == (5, 4)
    assert lida.celula(2, 0).texto == "ZR-1"  # a mesclada vale para as duas linhas
    assert lida.celula(4, 0).texto == "ZR-2"
    assert lida.celula(4, 1).texto == "Recuo frontal (m)"
    assert lida.celula(4, 3).texto == "4,00"

    corrido = TextoCorrido(documento)
    assert recortar(corrido, [lida]) == []  # o texto da tabela não vira trecho
