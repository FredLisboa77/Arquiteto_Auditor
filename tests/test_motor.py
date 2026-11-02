"""Testes da consistência entre documentos, do motor completo e do serviço de análise (Fase 9)."""

from pathlib import Path

import pytest

from arquiteto_auditor.dominio.constatacao import Constatacao, Situacao
from arquiteto_auditor.dominio.modelos import (
    Evidencia,
    OrigemValor,
    StatusConfirmacao,
    StatusItem,
    ValorExtraido,
)
from arquiteto_auditor.dominio.parametros import ParametroAdotado
from arquiteto_auditor.verificacao.consistencia import (
    mesmo_codigo,
    mesmo_nome,
    mesmo_texto,
    verificar_numeros,
    verificar_textos,
)
from arquiteto_auditor.verificacao.motor import Fatos, verificar


def _v(campo, valor, documento="pranchas.pdf", pendente=False, observacao=None):
    return ValorExtraido(
        campo=campo, valor=valor, origem=OrigemValor.VETORIAL, confianca=0.95,
        evidencias=[Evidencia(documento=documento, pagina=1, trecho=f"{campo} {valor}")],
        status=StatusConfirmacao.PENDENTE if pendente else StatusConfirmacao.AUTOMATICO,
        observacao=observacao)


def _p(chave, valor, fonte="prefeitura"):
    return ParametroAdotado(chave, _v(chave, valor, "lei.pdf"), fonte)


# ------------------------------------------------------------------ comparações


def test_comparacoes_de_texto():
    assert mesmo_codigo("81.753", "81753") and not mesmo_codigo("81.753", "81.735")
    assert mesmo_codigo("R00", "r00")
    assert mesmo_texto("Alameda das Hortênsias, 309",
                       "Alameda das Hortensias 309, Lote 40, Quadra G")
    assert mesmo_texto("3º Ofício de Registro de Imóveis de Nova Casa Gran",  # cortado no carimbo
                       "3º Ofício de Registro de Imóveis de Nova Casa Grande")
    assert not mesmo_texto("Rua A, 10", "Rua B, 10")
    assert mesmo_nome("Ana Souza", "ANA MARIA SOUZA") and not mesmo_nome("Ana Souza", "Ana Lima")


def test_numeros_iguais_divergentes_e_uma_fonte():
    igual = verificar_numeros("TERRENO_AREA", "área do terreno",
                              {"prancha": _v("A", 400.0), "matricula": _v("A", 400.005)}, 0.01)
    assert igual.status == StatusItem.ATENDE
    diferente = verificar_numeros("TERRENO_AREA", "área do terreno",
                                  {"prancha": _v("A", 357.7), "matricula": _v("A", 360.0)}, 0.01)
    assert diferente.status == StatusItem.DIVERGENTE
    assert "pranchas: 357,70 m² · matrícula: 360,00 m²" in diferente.mensagem
    uma = verificar_numeros("TERRENO_AREA", "área do terreno",
                            {"prancha": _v("A", 400.0), "memorial": None}, 0.01)
    assert uma.status == StatusItem.NAO_VERIFICAVEL and "não há com o que comparar" in uma.mensagem


def test_diferenca_com_leitura_incerta_nao_e_afirmada():
    item = verificar_textos("ID_ENDERECO", "endereço",
                            {"prancha": _v("E", "Travessa dos Flamboyants, 921"),
                             "memorial": _v("E", "Travessa dos Flamboyaits, 921", pendente=True)},
                            "texto")
    assert item.status == StatusItem.NAO_VERIFICAVEL and item.baixa_confianca
    assert "confirme" in item.mensagem


def test_ausente_em_todos_os_documentos():
    onde = [Evidencia(documento="pranchas.pdf", pagina=1, trecho="[não encontrado]")]
    item = verificar_textos("ID_RRT_ART", "RRT/ART", {"prancha": None, "memorial": None},
                            "codigo", ausente=StatusItem.NAO_ATENDE, onde_procurou=onde)
    assert item.status == StatusItem.NAO_ATENDE and item.evidencias == onde
    # Sem documento nenhum onde procurar, não dá para afirmar a ausência.
    sem_documentos = verificar_textos("ID_RRT_ART", "RRT/ART", {}, "codigo",
                                      ausente=StatusItem.NAO_ATENDE)
    assert sem_documentos.status == StatusItem.NAO_VERIFICAVEL


# ------------------------------------------------------------------ motor


def _fatos(**kw) -> Fatos:
    pranchas = {"MATRICULA": _v("MATRICULA", "81.753"), "TERRENO_AREA": _v("T", 400.0),
                "TERRENO_TESTADA": _v("T", 12.0), "AREA_PROJECAO": _v("P", 248.0),
                "AREA_CONSTR_PAV_1": _v("P1", 150.0), "AREA_CONSTR_PAV_2": _v("P2", 100.0),
                "AREA_CONSTR_TOTAL": _v("T", 250.0), "AREA_PERMEAVEL": _v("AP", 100.0),
                "TO_DECLARADA": _v("TO", 62.0, observacao=None),
                "RECUO_FRONTAL": _v("RF", 4.5), "ALTURA": _v("H", 7.0), "REVISAO": _v("R", "R00"),
                "AUTOR": _v("A", "Ana Souza"), "AUTOR_REGISTRO": _v("C", "CAU A1234-5"),
                "RRT": _v("RRT", "123")}
    pranchas.update(kw.pop("pranchas", {}))
    memorial = {"MATRICULA": _v("MATRICULA", "81.753", "memorial.pdf"),
                "AUTOR": _v("A", "Ana Souza", "memorial.pdf"),
                "AUTOR_REGISTRO": _v("C", "CAU A1234-5", "memorial.pdf"),
                "RRT": _v("RRT", "123", "memorial.pdf"),
                "ALTURA": _v("H", 9.5, "memorial.pdf")}
    memorial.update(kw.pop("memorial", {}))
    return Fatos(
        pranchas=pranchas, memorial=memorial,
        matricula={"TERRENO_AREA": _v("T", 400.0, "matricula.pdf"),
                   "MATRICULA": _v("MATRICULA", "81753", "matricula.pdf")},
        escritura=kw.pop("escritura", {}),
        parametros={"TO_MAX": _p("TO_MAX", 60.0), "RECUO_FRONTAL": _p("RECUO_FRONTAL", 5.0),
                    "ALTURA_MAX": _p("ALTURA_MAX", 9.0), "PAVIMENTOS_MAX": _p("PAVIMENTOS_MAX", 2),
                    "RECUO_FUNDOS": _p("RECUO_FUNDOS", 2.0)},
        constatacoes=kw.pop("constatacoes", []), arquivos_pranchas=["pranchas.pdf"], **kw)


def _itens(fatos) -> dict:
    return {(i.chave, i.escopo): i for i in verificar(fatos)}


def test_motor_gera_todo_o_catalogo_na_ordem():
    itens = verificar(_fatos())
    chaves = [i.chave for i in itens]
    assert chaves[0] == "ID_MATRICULA" and chaves.index("TERRENO_AREA") < chaves.index("TO_MAX")
    assert "AREA_CONSTR_MIN" not in chaves  # nenhum documento define o limite
    assert all(i.evidencias or i.status == StatusItem.NAO_VERIFICAVEL for i in itens)


def test_motor_aponta_os_erros_com_sugestao():
    itens = _itens(_fatos())
    assert itens[("ID_MATRICULA", None)].status == StatusItem.ATENDE
    to = itens[("TO_MAX", None)]
    assert to.status == StatusItem.NAO_ATENDE and "reduzir ≈ 8,00 m²" in to.sugestao
    assert itens[("RECUO_FRONTAL", None)].status == StatusItem.NAO_ATENDE
    assert itens[("PAVIMENTOS_MAX", None)].valor_projeto == 2  # contados no quadro
    assert itens[("AREA_CONSTR_SOMA", None)].status == StatusItem.ATENDE
    assert itens[("TO_DECLARADA", None)].status == StatusItem.ATENDE  # 248 ÷ 400 = 62%
    assert itens[("CA_MAX", None)].status == StatusItem.NAO_VERIFICAVEL  # sem parâmetro
    assert itens[("RECUO_FUNDOS", None)].status == StatusItem.NAO_VERIFICAVEL  # sem dado


def test_altura_do_memorial_quando_a_prancha_nao_traz():
    fatos = _fatos()
    del fatos.pranchas["ALTURA"]
    altura = _itens(fatos)[("ALTURA_MAX", None)]
    assert altura.status == StatusItem.NAO_ATENDE and altura.valor_projeto == 9.5
    assert altura.baixa_confianca
    assert "Valor do memorial: não encontrado nas pranchas." in altura.observacoes


def test_rrt_ausente_em_todos_os_documentos():
    fatos = _fatos()
    del fatos.pranchas["RRT"], fatos.memorial["RRT"]
    rrt = _itens(fatos)[("ID_RRT_ART", None)]
    assert rrt.status == StatusItem.NAO_ATENDE
    assert {e.documento for e in rrt.evidencias} == {"pranchas.pdf", "memorial.pdf"}


def test_area_da_escritura_vira_observacao_com_matricula():
    fatos = _fatos(escritura={"TERRENO_AREA": _v("T", 395.0, "escritura.pdf")})
    area = _itens(fatos)[("TERRENO_AREA", None)]
    assert area.status == StatusItem.ATENDE
    assert any("data da venda" in o for o in area.observacoes)


def test_matricula_divergente_e_revisao_diferente():
    fatos = _fatos(escritura={"MATRICULA": _v("MATRICULA", "81.735", "escritura.pdf")},
                   pranchas={"REVISAO": _v("R", "R01", pendente=True,
                                           observacao="Valores diferentes entre as folhas: R00.")})
    itens = _itens(fatos)
    assert itens[("ID_MATRICULA", None)].status == StatusItem.DIVERGENTE
    assert itens[("ID_REVISAO", None)].status == StatusItem.DIVERGENTE


def test_completude_vira_itens():
    constatacoes = [
        Constatacao("COTA_INDEFINIDA", Situacao.AUSENTE, "elemento=recuo_fundos",
                    motivo="linha de cota desenhada sem o número"),
        Constatacao("COTA_INDEFINIDA", Situacao.PRESENTE, "elemento=testada"),
        Constatacao("NORTE_INDICADO", Situacao.AUSENTE, motivo="nenhum \"N\" nas pranchas"),
        Constatacao("ASSINATURA_DIGITAL_VALIDA", Situacao.ALTERADA,
                    motivo="alterado depois de assinado"),
        Constatacao("ID_PROPRIETARIO", Situacao.AUSENTE, motivo="nome não encontrado"),
    ]
    itens = _itens(_fatos(constatacoes=constatacoes))
    cota = itens[("COTA_INDEFINIDA", "elemento=recuo_fundos")]
    assert cota.status == StatusItem.NAO_ATENDE
    assert cota.evidencias[0].trecho.startswith("[não encontrado:")
    assert ("COTA_INDEFINIDA", "elemento=testada") not in itens  # presente: nada a apontar
    assert itens[("NORTE_INDICADO", None)].status == StatusItem.NAO_ATENDE
    assert "alterado depois de assinado" in itens[("ASSINATURA_DIGITAL_VALIDA", None)].mensagem
    assert itens[("ID_PROPRIETARIO", None)].status == StatusItem.NAO_ATENDE
    assert itens[("ASSINATURA_AUTOR", None)].status == StatusItem.NAO_VERIFICAVEL  # sem dado
    fundos = itens[("RECUO_FUNDOS", None)]
    assert "Cota não indicada nas pranchas" in fundos.mensagem


# ------------------------------------------------------------------ serviço (base sintética)


@pytest.mark.parametrize("conjunto", ["sint-006"])
def test_analise_completa_sem_llm(conjunto, tmp_path):
    """Do PDF ao item, sem o Ollama: as tabelas da lei bastam neste conjunto."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from avaliar_verificacao import documentos_do_conjunto

    from arquiteto_auditor.ingestao.leitor import LeitorPDF
    from arquiteto_auditor.servicos.analise import analisar

    pasta = Path(__file__).resolve().parents[1] / "dados_sinteticos" / "projetos" / conjunto
    resultado = analisar(documentos_do_conjunto(pasta), leitor=LeitorPDF(), cliente=None)
    itens = {(i.chave, i.escopo): i for i in resultado.itens}
    assert resultado.lei.sem_llm and resultado.lei.zona.valor == "ZR-1"
    assert itens[("RECUO_FRONTAL", None)].status == StatusItem.NAO_ATENDE
    assert itens[("TO_MAX", None)].status == StatusItem.NAO_ATENDE
    assert itens[("ID_MATRICULA", None)].status == StatusItem.ATENDE
