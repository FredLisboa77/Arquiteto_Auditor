"""Testes da extração das pranchas (Fase 6)."""

from arquiteto_auditor.dominio.documento import DocumentoLido, PaginaLida, TipoPagina
from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    OrigemValor,
    StatusConfirmacao,
    TipoDocumento,
    ValorExtraido,
)
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


# ---------------------------------------------------------------- quadro de áreas

from arquiteto_auditor.extracao.pranchas.quadro import ler_quadro_areas  # noqa: E402


def _quadro(pagina) -> dict:
    return {v.campo: v.valor for v in ler_quadro_areas(pagina, "pranchas.pdf")}


def test_quadro_em_tabela_com_valor_a_direita():
    v = _quadro(_pagina(
        (100, 40, "QUADRO DE ÁREAS"),
        (100, 60, "Área do terreno"), (300, 60, "400,00 m²"),
        (100, 75, "Área construída térreo"), (300, 75, "119,97 m²"),
        (100, 90, "Área construída pav. superior"), (300, 90, "95,98 m²"),
        (100, 105, "Área construída total"), (300, 105, "215,95 m²"),
        (100, 120, "Área de projeção"), (300, 120, "119,97 m²"),
        (100, 135, "Área permeável"), (300, 135, "112,00 m²"),
        (100, 150, "Taxa de ocupação"), (300, 150, "29,99 %"),
        (100, 165, "Coeficiente de aproveitamento"), (300, 165, "0,54"),
        (100, 180, "Taxa de permeabilidade"), (300, 180, "28,00 %"),
    ))
    assert v == {"TERRENO_AREA": 400.0, "AREA_CONSTR_PAV_1": 119.97, "AREA_CONSTR_PAV_2": 95.98,
                 "AREA_CONSTR_TOTAL": 215.95, "AREA_PROJECAO": 119.97, "AREA_PERMEAVEL": 112.0,
                 "TO_DECLARADA": 29.99, "CA_DECLARADO": 0.54, "PERMEAVEL_DECLARADA": 28.0}


def test_quadro_em_texto_corrido_com_pontilhado_e_valor_antes_do_rotulo():
    v = _quadro(_pagina((100, 60, "Área do lote .................. 400,00 m²"),
                        (100, 75, "119,97 m² — Área coberta térreo"),
                        (100, 90, "0,54 — Índice de aproveitamento")))
    assert v == {"TERRENO_AREA": 400.0, "AREA_CONSTR_PAV_1": 119.97, "CA_DECLARADO": 0.54}


def test_quadro_em_celulas_e_indices_na_mesma_linha():
    v = _quadro(_pagina((100, 60, "Área do terreno"), (200, 60, "Área permeável"),
                        (100, 72, "400,00"), (200, 72, "112,00"),
                        (100, 100, "T.O. = 29,99%   C.A. = 0,54   T.P. = 28,00%")))
    assert v == {"TERRENO_AREA": 400.0, "AREA_PERMEAVEL": 112.0, "TO_DECLARADA": 29.99,
                 "CA_DECLARADO": 0.54, "PERMEAVEL_DECLARADA": 28.0}


def test_quadro_estilo_autocad_com_rotulo_quebrado_e_codigos():
    v = _quadro(_pagina((100, 60, "ÁREA CONSTRUÍDA"), (300, 60, "A=119.97m²"),
                        (100, 70, "TÉRREO"),
                        (100, 85, "TAXA DE"), (300, 85, "29.99%%%"), (100, 95, "OCUPAÇÃO"),
                        (100, 110, "COEFICIENTE DE"), (300, 110, "C=0.54"),
                        (100, 120, "APROVEITAMENTO"),
                        (100, 135, "ALTURA DA"), (300, 135, "H=6.50m"), (100, 145, "EDIFICAÇÃO")))
    assert v == {"AREA_CONSTR_PAV_1": 119.97, "TO_DECLARADA": 29.99, "CA_DECLARADO": 0.54,
                 "ALTURA": 6.5}


def test_quadro_ignora_distracoes_e_unidade_errada():
    v = _quadro(_pagina((100, 60, "SALA"), (100, 72, "A = 38.15m²"),  # área de ambiente
                        (300, 60, "LOTE 6"), (300, 72, "200.16 m²"),  # lote vizinho
                        (100, 100, "Taxa de ocupação"), (300, 100, "29,99 m²")))  # unidade errada
    assert v == {}


def test_quadro_ignora_titulos_e_textos_do_desenho_com_palavras_do_rotulo():
    v = _quadro(_pagina((100, 60, "PLANTA BAIXA — PAVIMENTO SUPERIOR — ESCALA 1:100"),
                        (100, 90, "PROJEÇÃO DA COBERTURA"), (300, 90, "12,97"),
                        (100, 120, "ÁREA PERMEÁVEL (GRAMA)"), (100, 132, "112,00 m²")))
    assert v == {}


# ---------------------------------------------------------------- texto girado e cotas


def _vertical(x: float, y_base: float, texto: str) -> list[Palavra]:
    """Texto girado 90° (lido de baixo para cima): cada palavra fica "em pé"."""
    palavras, y = [], y_base
    for token in texto.split():
        comprimento = 4.5 * len(token)
        palavras.append(Palavra(texto=token, bbox=(x, y - comprimento, x + ALTURA, y),
                                confianca=1.0, origem=OrigemPalavra.VETORIAL))
        y -= comprimento + 2.5
    return palavras


def test_agrupar_linhas_le_texto_girado_de_baixo_para_cima():
    palavras = _vertical(500, 400, "RECUO FRONTAL 6,00") + _escrever(100, 50, "18")
    linhas = agrupar_linhas(palavras)
    assert sorted(ln.texto for ln in linhas) == ["18", "RECUO FRONTAL 6,00"]
    girada = next(ln for ln in linhas if ln.vertical)
    assert girada.altura == ALTURA  # altura da letra = largura da palavra em pé


def test_cotas_com_rotulo_deitadas_giradas_e_notacao_cad():
    palavras = (_escrever(100, 50, "LATERAL ESQ. 1,75") + _escrever(300, 50, "TESTADA 12.50")
                + _vertical(500, 400, "RECUO FRONTAL 6,00")
                + _escrever(100, 200, "MURO H=1.80m"))
    pagina = PaginaLida(numero=1, largura=2384, altura=1684, tipo=TipoPagina.VETORIAL,
                        palavras=palavras)
    assert _quadro(pagina) == {"RECUO_LATERAL_E": 1.75, "TERRENO_TESTADA": 12.5,
                               "RECUO_FRONTAL": 6.0, "MURO_ALTURA": 1.8}


def test_rotulo_de_cota_solto_nao_puxa_numero_vizinho():
    assert _quadro(_pagina((100, 50, "MURO"), (100, 62, "1,80"), (100, 90, "TESTADA"),
                           (200, 90, "12,50"))) == {}


def test_palavra_curta_no_meio_do_texto_girado():
    # "DE" em pé é quase quadrado: só pela forma não dá para saber que está girado
    palavras = [Palavra(texto=t, bbox=(500, y0, 508, y1), confianca=1.0,
                        origem=OrigemPalavra.VETORIAL)
                for t, y0, y1 in (("RECUO", 370, 400), ("DE", 357, 367), ("FUNDOS", 318, 354),
                                  ("13,03", 290, 315))]
    (linha,) = agrupar_linhas(palavras)
    assert linha.vertical and linha.texto == "RECUO DE FUNDOS 13,03"


# ---------------------------------------------------------------- cotas sem rótulo

from arquiteto_auditor.extracao.pranchas.cotas import ler_cotas_sem_rotulo  # noqa: E402


def _situacao(rua_y: float, com_fundos: bool = True) -> PaginaLida:
    """Lote de 12,50 × 32,00 desenhado com cadeias de cotas (sem rótulo) e a rua."""
    palavras = (_escrever(300, 100, "12.50")  # total horizontal (testada)
                + _escrever(240, 115, "1.75") + _escrever(300, 115, "9.25")
                + _escrever(370, 115, "1.50")  # cadeia horizontal (esq → dir na folha)
                + _vertical(420, 480, "6.00") + _vertical(420, 330, "12.97")  # cadeia vertical
                + _vertical(440, 330, "32.00")  # total vertical (profundidade)
                + _escrever(280, rua_y, "RUA DAS ACÁCIAS"))
    if com_fundos:
        palavras += _vertical(420, 170, "13.03")
    return PaginaLida(numero=1, largura=2384, altura=1684, tipo=TipoPagina.VETORIAL,
                      palavras=palavras)


def _cotas(pagina) -> dict:
    return {v.campo: v.valor for v in ler_cotas_sem_rotulo(pagina, "pranchas.pdf")}


def test_cadeias_de_cotas_com_a_rua_embaixo():
    valores = ler_cotas_sem_rotulo(_situacao(rua_y=560), "pranchas.pdf")
    assert {v.campo: v.valor for v in valores} == {
        "RECUO_LATERAL_E": 1.75, "RECUO_LATERAL_D": 1.5, "TERRENO_TESTADA": 12.5,
        "RECUO_FRONTAL": 6.0, "RECUO_FUNDOS": 13.03, "TERRENO_PROFUNDIDADE": 32.0}
    assert all(v.status == StatusConfirmacao.PENDENTE for v in valores)  # sempre confirmar


def test_cadeias_de_cotas_com_a_rua_em_cima_invertem_frente_e_lados():
    v = _cotas(_situacao(rua_y=40))
    assert v["RECUO_FRONTAL"] == 13.03 and v["RECUO_FUNDOS"] == 6.0
    assert v["RECUO_LATERAL_E"] == 1.5 and v["RECUO_LATERAL_D"] == 1.75


def test_cadeia_incompleta_ou_sem_rua_nao_afirma_nada():
    v = _cotas(_situacao(rua_y=560, com_fundos=False))
    assert "RECUO_FRONTAL" not in v and "RECUO_FUNDOS" not in v
    assert v["RECUO_LATERAL_E"] == 1.75  # a cadeia horizontal está completa
    sem_rua = _situacao(rua_y=560)
    sem_rua = sem_rua.model_copy(update={"palavras": [
        p for p in sem_rua.palavras if p.texto not in ("RUA", "DAS", "ACÁCIAS")]})
    assert _cotas(sem_rua) == {}


def test_muro_sem_rotulo_pega_a_cota_girada_mais_proxima():
    palavras = (_escrever(100, 300, "MURO") + _vertical(90, 360, "1.80")
                + _vertical(400, 380, "2.80"))  # pé-direito, longe
    pagina = PaginaLida(numero=1, largura=2384, altura=1684, tipo=TipoPagina.VETORIAL,
                        palavras=palavras)
    (valor,) = ler_cotas_sem_rotulo(pagina, "pranchas.pdf")
    assert valor.campo == "MURO_ALTURA" and valor.valor == 1.8
    assert valor.status == StatusConfirmacao.PENDENTE


def test_valores_que_concordam_ficam_com_o_mais_confiavel():
    from arquiteto_auditor.extracao.pranchas.extrator import _consolidar

    def valor(confianca, status):
        return ValorExtraido(campo="RECUO_FRONTAL", valor=6.0, origem=OrigemValor.VETORIAL,
                             confianca=confianca, status=status, evidencias=[Evidencia(
                                 documento="p.pdf", pagina=1, trecho="6,00")])

    r = _consolidar("RECUO_FRONTAL", [valor(0.6, StatusConfirmacao.PENDENTE),
                                      valor(0.95, StatusConfirmacao.AUTOMATICO)])
    assert r.status == StatusConfirmacao.AUTOMATICO and r.confianca == 0.95
    assert len(r.evidencias) == 2
