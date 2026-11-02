"""Testes da leitura da matrícula e da escritura (Fase 7)."""

from arquiteto_auditor.dominio.documento import DocumentoLido, PaginaLida, TipoPagina
from arquiteto_auditor.dominio.modelos import TipoDocumento
from arquiteto_auditor.extracao.registro import ler_matricula


def test_matricula_vazia_nao_inventa_atos():
    pagina = PaginaLida(numero=1, largura=612, altura=792, tipo=TipoPagina.ESCANEADA)
    documento = DocumentoLido(arquivo="matricula.pdf", hash_sha256="0" * 64, paginas=[pagina],
                              tipo=TipoDocumento.MATRICULA)
    lida = ler_matricula(documento)
    assert lida.atos == [] and lida.estado_atual == {}


# ---------------------------------------------------------------- texto corrido

from arquiteto_auditor.dominio.documento import OrigemPalavra, Palavra  # noqa: E402
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido  # noqa: E402


def _pagina_ocr(numero: int, linhas: list[str], confianca: float = 0.9) -> PaginaLida:
    """Página escaneada com as linhas dadas (uma palavra por token, posições fictícias)."""
    palavras = []
    for i, linha in enumerate(linhas):
        x = 50.0
        for token in linha.split():
            palavras.append(Palavra(texto=token, bbox=(x, 50 + 15 * i, x + 5 * len(token),
                                                       60 + 15 * i),
                                    confianca=confianca, origem=OrigemPalavra.OCR,
                                    bloco=1, linha=i))
            x += 5 * len(token) + 4
    return PaginaLida(numero=numero, largura=612, altura=792, tipo=TipoPagina.ESCANEADA,
                      palavras=palavras)


def _documento(*paginas: PaginaLida, tipo=TipoDocumento.MATRICULA) -> DocumentoLido:
    return DocumentoLido(arquivo="matricula.pdf", hash_sha256="0" * 64, paginas=list(paginas),
                         tipo=tipo)


def test_texto_corrido_liga_trecho_a_pagina_e_posicao():
    texto = TextoCorrido(_documento(_pagina_ocr(1, ["IMÓVEL: lote 40", "área de 360,00 m²"]),
                                    _pagina_ocr(2, ["R-1/81.735 - Em 30 de outubro de 2015."],
                                                confianca=0.4)))
    assert texto.texto == ("IMÓVEL: lote 40\nárea de 360,00 m²\n"
                           "R-1/81.735 - Em 30 de outubro de 2015.")
    inicio = texto.texto.index("360,00")
    evidencia = texto.evidencia(inicio, inicio + 6, "matricula.pdf")
    assert evidencia.pagina == 1 and evidencia.trecho == "360,00"
    assert evidencia.bbox[1] == 65  # a 2ª linha da página
    inicio = texto.texto.index("R-1")
    assert texto.evidencia(inicio, inicio + 10, "matricula.pdf").pagina == 2
    assert texto.confianca(inicio, inicio + 10) == 0.4


# ---------------------------------------------------------------- atos da matrícula

from datetime import date  # noqa: E402

from arquiteto_auditor.dominio.registro import TipoAto  # noqa: E402

MATRICULA = [
    ["REGISTRO DE IMÓVEIS DE VILA NOVA", "MATRÍCULA Nº 12.345 - LIVRO Nº 2",
     "IMÓVEL: Lote 7 da Quadra B, com a área de 300,00 m² (trezentos metros",
     "quadrados). PROPRIETÁRIA: Alfa Loteadora Ltda. O Oficial.",
     "R-1/12.345 - Em 10 de maio de 2012. COMPRA E VENDA: Alfa Loteadora Ltda.",
     "transmitiu o imóvel, por venda, a João Lima, brasileiro. O Oficial.",
     "AV.2/12.345 - Em 05 de junho de 2013. RETIFICAÇÃO DE ÁREA: a descrição",
     "passa a ser a seguinte: área de 312,50 m². O Oficial.",
     "R-3/12.345 - Em 02 de julho de 2014. Por instrumento particular, o proprietário",
     "alienou fiduciariamente o imóvel ao Banco Beta S.A. O Oficial."],
    ["MATRÍCULA Nº 12.345 - FICHA 02",
     "AV-4/12.345 - Em 09 de agosto de 2015. CANCELAMENTO: Fica cancelado o registro",
     "R-3/12.345, por autorização do credor. O Oficial.",
     "AV-5/12.345 - Em 1º de março de 2016. AVERBAÇÃO DE CASAMENTO: o proprietário",
     "casou-se. O Oficial.",
     "CERTIDÃO - Certifico que a presente é reprodução autêntica. O Oficial."],
]


def _matricula(paginas=MATRICULA, confianca=0.95):
    return _documento(*[_pagina_ocr(i + 1, linhas, confianca)
                        for i, linhas in enumerate(paginas)])


def test_separa_os_atos_em_ordem_com_data_e_tipo():
    lida = ler_matricula(_matricula())
    assert lida.numero == "12.345"
    assert [(a.codigo, a.tipo, a.data) for a in lida.atos] == [
        ("ABERTURA", TipoAto.ABERTURA, None),
        ("R-1", TipoAto.COMPRA_E_VENDA, date(2012, 5, 10)),
        ("AV-2", TipoAto.RETIFICACAO, date(2013, 6, 5)),
        ("R-3", TipoAto.ALIENACAO_FIDUCIARIA, date(2014, 7, 2)),  # sem título: palavras-chave
        ("AV-4", TipoAto.CANCELAMENTO, date(2015, 8, 9)),  # a referência ao R-3 não é ato
        ("AV-5", TipoAto.OUTRO, date(2016, 3, 1)),
    ]
    assert "casou-se" in lida.atos[-1].texto and "Certifico" not in lida.atos[-1].texto
    assert lida.atos[4].evidencia.pagina == 2


def test_ato_nao_compreendido_vira_pendencia():
    lida = ler_matricula(_matricula())
    assert any("AV-5" in p for p in lida.pendencias)


def test_salto_na_numeracao_vira_pendencia():
    paginas = [MATRICULA[0][:6] + MATRICULA[0][8:]]  # some o AV-2 (página ilegível, p.ex.)
    lida = ler_matricula(_matricula(paginas))
    assert [a.codigo for a in lida.atos] == ["ABERTURA", "R-1", "R-3"]
    assert any("AV-2" in p or "2" in p for p in lida.pendencias)


def test_cabecalhos_com_sujeira_de_ocr():
    paginas = [["IMÓVEL: Lote 7, área de 300,00 m². PROPRIETÁRIA: Alfa Ltda.",
                "R-I/12.345 - Em 10 de maio de 2012. COMPRA E VENDA: transmitiu a João.",
                "A V-2/12.345 - Em 05 de junho de 2013. riGricIR Are: procede-se à",
                "retificação da descrição do imóvel. O Oficial.",
                "R-=3/12.345 - Em 02 de julho de 2014. ALIENAÇÃO FIDUCIÁRIA: ao Banco."]]
    lida = ler_matricula(_matricula(paginas))
    assert [(a.codigo, a.tipo) for a in lida.atos[1:]] == [
        ("R-1", TipoAto.COMPRA_E_VENDA), ("AV-2", TipoAto.RETIFICACAO),
        ("R-3", TipoAto.ALIENACAO_FIDUCIARIA)]
    assert lida.atos[2].confianca < lida.atos[1].confianca  # tipo só pelo corpo do texto


def test_nova_descricao_do_imovel_indica_retificacao_mesmo_sem_a_palavra():
    paginas = [["IMÓVEL: Lote 7, área de 300,00 m². PROPRIETÁRIA: Alfa Ltda.",
                "AV-1/12.345 - Em 05 de junho de 2013. xXx Ar: a pedido do proprietário,",
                "a descrição do imóvel passa a ser a seguinte: área de 312,50 m²."]]
    assert ler_matricula(_matricula(paginas)).atos[1].tipo == TipoAto.RETIFICACAO
