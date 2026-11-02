"""Testes da leitura do memorial descritivo (Fase 7)."""

from arquiteto_auditor.dominio.documento import (
    DocumentoLido,
    OrigemPalavra,
    PaginaLida,
    Palavra,
    TipoPagina,
)
from arquiteto_auditor.dominio.modelos import StatusConfirmacao, TipoDocumento
from arquiteto_auditor.extracao.frases import ler_frases
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido


def _pagina(linhas: list[str], origem=OrigemPalavra.VETORIAL, confianca=1.0) -> PaginaLida:
    palavras = []
    for i, linha in enumerate(linhas):
        x = 50.0
        for token in linha.split():
            palavras.append(Palavra(texto=token, bbox=(x, 50 + 15 * i, x + 5 * len(token),
                                                       60 + 15 * i),
                                    confianca=confianca, origem=origem, bloco=1, linha=i))
            x += 5 * len(token) + 4
    tipo = TipoPagina.ESCANEADA if origem == OrigemPalavra.OCR else TipoPagina.VETORIAL
    return PaginaLida(numero=1, largura=595, altura=842, tipo=tipo, palavras=palavras)


def _documento(*paginas) -> DocumentoLido:
    return DocumentoLido(arquivo="memorial.pdf", hash_sha256="0" * 64, paginas=list(paginas),
                         tipo=TipoDocumento.MEMORIAL)


def _frases(linhas, **kw) -> dict:
    corrido = TextoCorrido(_documento(_pagina(linhas, **kw)))
    return {v.campo: v.valor for v in ler_frases(corrido, "memorial.pdf")}


def test_frases_do_memorial_estruturado():
    assert _frases([
        "O terreno possui área de 400,00 m², conforme matrícula, com testada de 12,50 m",
        "para a via interna e profundidade de 32,00 m. O terreno é plano.",
        "A altura total da edificação, medida do nível do passeio ao ponto mais alto da",
        "cobertura, é de 6,50 m. O muro de divisa terá altura de 1,80 m, em alvenaria.",
    ]) == {"TERRENO_AREA": 400.0, "TERRENO_TESTADA": 12.5, "TERRENO_PROFUNDIDADE": 32.0,
           "ALTURA": 6.5, "MURO_ALTURA": 1.8}


def test_frases_do_memorial_narrativo():
    assert _frases([
        "A edificação em questão possui área construída total de 215,95m², a área",
        "permeável é de 112,00m², resultando uma taxa de permeabilidade de 28,00%; a taxa",
        "de ocupação é 29,99%, coeficiente de aproveitamento 0,54, totalizando 6,50m de",
        "altura.",
    ]) == {"AREA_CONSTR_TOTAL": 215.95, "AREA_PERMEAVEL": 112.0, "PERMEAVEL_DECLARADA": 28.0,
           "TO_DECLARADA": 29.99, "CA_DECLARADO": 0.54, "ALTURA": 6.5}


def test_frases_ignoram_especificacoes_tecnicas():
    assert _frases([
        "ESTRUTURA: pilares e lajes em concreto armado (fck 25 MPa); pé-direito de 2,80 m.",
        "PISCINA: em concreto armado, com área de 24,00 m² e profundidade de 1,40 m.",
        "INSTALAÇÕES: reservatório de água de 1.000 litros.",
    ]) == {}


def test_frase_lida_por_ocr_com_baixa_confianca_fica_pendente():
    corrido = TextoCorrido(_documento(_pagina(["O terreno possui área de 400,00 m²."],
                                              origem=OrigemPalavra.OCR, confianca=0.3)))
    (valor,) = ler_frases(corrido, "memorial.pdf")
    assert valor.status == StatusConfirmacao.PENDENTE and "400,00" in valor.evidencias[0].trecho


def test_autor_pelo_bloco_de_assinatura():
    from arquiteto_auditor.extracao.memorial import ler_memorial
    documento = _documento(_pagina(["Quadro de áreas:", "______________________",
                                    "IAN NASCIMENTO CAMARGO",
                                    "Arquiteto(a) e Urbanista - CAU A291720-1"]))
    valores = ler_memorial(documento)
    assert valores["AUTOR"].valor == "IAN NASCIMENTO CAMARGO"
    assert valores["AUTOR_REGISTRO"].valor == "CAU A291720-1"


def test_linha_acima_do_registro_que_nao_parece_nome_e_ignorada():
    from arquiteto_auditor.extracao.memorial import ler_memorial
    documento = _documento(_pagina(["Proprietário(a)Valentim Azevedo", "CAU A286237-7"]))
    valores = ler_memorial(documento)
    assert "AUTOR" not in valores and valores["AUTOR_REGISTRO"].valor == "CAU A286237-7"
