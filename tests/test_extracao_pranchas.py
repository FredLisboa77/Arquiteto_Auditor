"""Testes da extração das pranchas (Fase 6)."""

from arquiteto_auditor.dominio.documento import DocumentoLido, PaginaLida, TipoPagina
from arquiteto_auditor.dominio.modelos import StatusConfirmacao, TipoDocumento
from arquiteto_auditor.extracao.pranchas import extrair_pranchas


def _documento(tipo: TipoDocumento) -> DocumentoLido:
    pagina = PaginaLida(numero=1, largura=2384, altura=1684, tipo=TipoPagina.VETORIAL)
    return DocumentoLido(arquivo="x.pdf", hash_sha256="0" * 64, paginas=[pagina], tipo=tipo)


def test_sem_pranchas_nao_extrai_nada():
    assert extrair_pranchas([_documento(TipoDocumento.MATRICULA)]) == {}


def test_prancha_vazia_nao_inventa_valores():
    assert extrair_pranchas([_documento(TipoDocumento.PRANCHA)]) == {}


# ---------------------------------------------------------------- linhas e carimbo

from arquiteto_auditor.dominio.documento import OrigemPalavra, Palavra  # noqa: E402
from arquiteto_auditor.extracao.pranchas.carimbo import ler_carimbo  # noqa: E402
from arquiteto_auditor.extracao.pranchas.linhas import agrupar_linhas  # noqa: E402

ALTURA = 8.0  # altura do texto em pontos


def _escrever(x: float, y: float, texto: str, origem=OrigemPalavra.VETORIAL) -> list[Palavra]:
    """Palavras de um texto escrito a partir de (x, y), largura ~ 4,5 pt por caractere."""
    palavras = []
    for token in texto.split():
        largura = 4.5 * len(token)
        palavras.append(Palavra(texto=token, bbox=(x, y, x + largura, y + ALTURA),
                                confianca=1.0, origem=origem))
        x += largura + 2.5
    return palavras


def _pagina(*textos) -> PaginaLida:
    palavras = [p for x, y, t in textos for p in _escrever(x, y, t)]
    return PaginaLida(numero=1, largura=2384, altura=1684, tipo=TipoPagina.VETORIAL,
                      palavras=palavras)


def _valores(pagina) -> dict:
    return {v.campo: v.valor for v in ler_carimbo(pagina, "pranchas.pdf")}


def test_agrupar_linhas_separa_rotulo_e_valor_distantes():
    pagina = _pagina((100, 50, "LOTE / QUADRA:"), (250, 50.5, "19 / H"), (100, 70, "MUNICÍPIO:"))
    linhas = agrupar_linhas(pagina.palavras)
    assert [ln.texto for ln in linhas] == ["LOTE / QUADRA:", "19 / H", "MUNICÍPIO:"]


def test_carimbo_com_rotulo_a_esquerda():
    pagina = _pagina(
        (100, 50, "PROJETO:"), (250, 50, "RESIDÊNCIA NOGUEIRA"),
        (100, 67, "CONDOMÍNIO:"), (250, 67, "Condomínio Dias"),
        (100, 84, "LOTE / QUADRA:"), (250, 84, "19 / H"),
        (100, 101, "MATRÍCULA:"), (250, 101, "71.677 — 3º Ofício de Registro de Imóveis"),
        (100, 118, "PROPRIETÁRIO:"), (250, 118, "Milena Cunha Pereira"),
        (100, 135, "AUTOR DO PROJETO:"), (250, 135, "Elisa Martins Aragão"),
        (100, 152, "REGISTRO:"), (250, 152, "CAU A198048-7"),
        (100, 169, "RRT:"), (250, 169, "10814047"),
        (100, 186, "REVISÃO:"),  # em branco
        (100, 203, "ESCALA:"), (250, 203, "INDICADA"),
        (120, 240, "AUTOR DO PROJETO"), (300, 240, "PROPRIETÁRIO"),  # assinaturas
    )
    v = _valores(pagina)
    assert v["TITULO"] == "RESIDÊNCIA NOGUEIRA"
    assert v["CONDOMINIO"] == "Condomínio Dias"
    assert v["LOTE"] == "19" and v["QUADRA"] == "H"
    assert v["MATRICULA"] == "71.677" and v["CARTORIO"] == "3º Ofício de Registro de Imóveis"
    assert v["PROPRIETARIO"] == "Milena Cunha Pereira"
    assert v["AUTOR"] == "Elisa Martins Aragão" and v["AUTOR_REGISTRO"] == "CAU A198048-7"
    assert v["RRT"] == "10814047"
    assert "REVISAO" not in v  # campo em branco: não pega o valor de outra linha


def test_carimbo_com_rotulo_acima_do_valor():
    pagina = _pagina(
        (100, 50, "OBRA"), (100, 62, "RESIDÊNCIA SOUZA"),
        (100, 80, "INTERESSADO"), (100, 92, "Ana Lima — CPF 123.456.789-00"),
        (100, 110, "REV."), (100, 140, "ESCALA"), (100, 152, "INDICADA"),
    )
    v = _valores(pagina)
    assert v["TITULO"] == "RESIDÊNCIA SOUZA"
    assert v["PROPRIETARIO"] == "Ana Lima"  # o CPF nunca é guardado
    assert "REVISAO" not in v


def test_carimbo_cpf_nao_aparece_na_evidencia():
    pagina = _pagina((100, 50, "PROPRIETÁRIO:"), (250, 50, "Ana Lima — CPF 123.456.789-00"))
    (valor,) = ler_carimbo(pagina, "pranchas.pdf")
    assert "123.456" not in valor.evidencias[0].trecho
    assert valor.evidencias[0].pagina == 1 and valor.evidencias[0].bbox is not None


def test_rotulo_e_valor_na_mesma_linha():
    pagina = _pagina((100, 50, "Proprietário: João da Silva"), (100, 70, "Revisão: R02"))
    v = _valores(pagina)
    assert v["PROPRIETARIO"] == "João da Silva" and v["REVISAO"] == "R02"


def _prancha(*paginas: PaginaLida) -> DocumentoLido:
    return DocumentoLido(arquivo="pranchas.pdf", hash_sha256="0" * 64, paginas=list(paginas),
                         tipo=TipoDocumento.PRANCHA)


def _folha(numero: int, revisao: str) -> PaginaLida:
    pagina = _pagina((100, 50, "PROJETO:"), (250, 50, "RESIDÊNCIA X"),
                     (100, 67, "REVISÃO:"), (250, 67, revisao))
    return pagina.model_copy(update={"numero": numero})


def test_folhas_que_concordam_somam_evidencias():
    r = extrair_pranchas([_prancha(_folha(1, "R00"), _folha(2, "R00"))])
    assert r["TITULO"].valor == "RESIDÊNCIA X"
    assert [e.pagina for e in r["TITULO"].evidencias] == [1, 2]
    assert r["TITULO"].status == StatusConfirmacao.AUTOMATICO


def test_folhas_que_discordam_ficam_pendentes_com_o_valor_mais_frequente():
    r = extrair_pranchas([_prancha(_folha(1, "R00"), _folha(2, "R01"), _folha(3, "R00"))])
    assert r["REVISAO"].valor == "R00"
    assert r["REVISAO"].status == StatusConfirmacao.PENDENTE
    assert "R01" in r["REVISAO"].observacao


def test_carimbo_com_celulas_altas_e_valor_no_pe_da_celula():
    pagina = _pagina((100, 50, "PROPRIETÁRIO"), (100, 110, "Ana Lima"),
                     (100, 130, "REVISÃO"), (100, 190, "ESCALA"), (100, 250, "INDICADA"))
    v = _valores(pagina)
    assert v["PROPRIETARIO"] == "Ana Lima"
    assert "REVISAO" not in v  # o primeiro texto abaixo é outro rótulo: campo em branco
