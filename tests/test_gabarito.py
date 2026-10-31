"""Testes do formato e do validador de gabarito."""

import json
from pathlib import Path

import pytest

from arquiteto_auditor.avaliacao.gabarito import GabaritoInvalido, carregar_gabarito, esquema_json
from arquiteto_auditor.dominio.modelos import StatusItem

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLO = RAIZ / "docs" / "esquemas" / "exemplo_gabarito.json"
ESQUEMA = RAIZ / "docs" / "esquemas" / "gabarito.schema.json"


def gabarito_minimo(**alteracoes):
    dados = {
        "conjunto": "sint-001",
        "versao_gabarito": 1,
        "rodada": "R00",
        "itens_esperados": [
            {"chave": "TO_MAX", "status": "nao_atende", "valor_projeto": 62.0, "limite": 60.0},
        ],
    }
    return dados | alteracoes


def salvar(tmp_path, dados):
    arquivo = tmp_path / "gabarito.json"
    texto = dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False)
    arquivo.write_text(texto, encoding="utf-8")
    return arquivo


def mensagem_de_erro(tmp_path, dados) -> str:
    with pytest.raises(GabaritoInvalido) as erro:
        carregar_gabarito(salvar(tmp_path, dados))
    return str(erro.value)


# ---------------------------------------------------------------- casos válidos


def test_exemplo_documentado_e_valido():
    gabarito = carregar_gabarito(EXEMPLO)
    assert gabarito.conjunto == "sint-exemplo-r01"
    assert gabarito.erros_esperados()  # tem erros para medir revocação


def test_gabarito_minimo_valido(tmp_path):
    gabarito = carregar_gabarito(salvar(tmp_path, gabarito_minimo()))
    assert gabarito.itens_esperados[0].status == StatusItem.NAO_ATENDE


def test_erros_esperados_sao_nao_atende_e_divergente(tmp_path):
    itens = [
        {"chave": "TO_MAX", "status": "nao_atende"},
        {"chave": "ID_MATRICULA", "status": "divergente"},
        {"chave": "RECUO_FRONTAL", "status": "atende"},
        {"chave": "ALTURA_MAX", "status": "nao_verificavel"},
    ]
    gabarito = carregar_gabarito(salvar(tmp_path, gabarito_minimo(itens_esperados=itens)))
    assert {i.chave for i in gabarito.erros_esperados()} == {"TO_MAX", "ID_MATRICULA"}


def test_esquema_json_publicado_esta_atualizado():
    # Se falhar: rode  python scripts/gerar_esquema_gabarito.py
    assert json.loads(ESQUEMA.read_text(encoding="utf-8")) == esquema_json()


# ---------------------------------------------------------------- erros com mensagem clara


def test_json_malformado_indica_a_linha(tmp_path):
    assert "linha 2" in mensagem_de_erro(tmp_path, '{\n  "conjunto": ,\n}')


def test_campo_obrigatorio_ausente(tmp_path):
    dados = gabarito_minimo()
    del dados["rodada"]
    assert "rodada: campo obrigatório ausente" in mensagem_de_erro(tmp_path, dados)


def test_status_invalido_lista_os_permitidos(tmp_path):
    dados = gabarito_minimo(itens_esperados=[{"chave": "TO_MAX", "status": "reprovado"}])
    mensagem = mensagem_de_erro(tmp_path, dados)
    assert "itens_esperados[0].status" in mensagem
    assert "'reprovado'" in mensagem
    assert "nao_atende" in mensagem


def test_campo_desconhecido(tmp_path):
    mensagem = mensagem_de_erro(tmp_path, gabarito_minimo(observacao="x"))
    assert "observacao: campo desconhecido" in mensagem


def test_codigo_de_rodada_invalido(tmp_path):
    assert "rodada" in mensagem_de_erro(tmp_path, gabarito_minimo(rodada="R1"))


def test_chave_fora_do_catalogo(tmp_path):
    dados = gabarito_minimo(itens_esperados=[{"chave": "TAXA_X", "status": "atende"}])
    assert "TAXA_X" in mensagem_de_erro(tmp_path, dados)


def test_escopo_obrigatorio_para_chave_por_pavimento(tmp_path):
    dados = gabarito_minimo(itens_esperados=[{"chave": "AREA_CONSTR_PAV", "status": "atende"}])
    assert "escopo" in mensagem_de_erro(tmp_path, dados)


def test_escopo_proibido_para_chave_sem_escopo(tmp_path):
    item = {"chave": "TO_MAX", "escopo": "pavimento=1", "status": "atende"}
    assert "escopo" in mensagem_de_erro(tmp_path, gabarito_minimo(itens_esperados=[item]))


def test_item_duplicado(tmp_path):
    item = {"chave": "TO_MAX", "status": "atende"}
    dados = gabarito_minimo(itens_esperados=[item, item])
    assert "duplicado" in mensagem_de_erro(tmp_path, dados)


def test_r00_nao_tem_comparacao_com_rodada_anterior(tmp_path):
    dados = gabarito_minimo(
        comparacao_rodada_anterior=[{"chave": "TO_MAX", "resultado": "pendente"}]
    )
    assert "R00" in mensagem_de_erro(tmp_path, dados)


def test_r01_com_comparacao_exige_conjunto_anterior(tmp_path):
    dados = gabarito_minimo(
        rodada="R01", comparacao_rodada_anterior=[{"chave": "TO_MAX", "resultado": "pendente"}]
    )
    assert "conjunto_anterior" in mensagem_de_erro(tmp_path, dados)


def test_fonte_de_valor_desconhecida(tmp_path):
    dados = gabarito_minimo(valores_esperados={"TERRENO_AREA": {"planilha": 450.0}})
    assert "planilha" in mensagem_de_erro(tmp_path, dados)


def test_varios_erros_aparecem_juntos(tmp_path):
    dados = gabarito_minimo(rodada="X", versao_gabarito=0)
    mensagem = mensagem_de_erro(tmp_path, dados)
    assert "rodada" in mensagem
    assert "versao_gabarito" in mensagem


def _gabarito_com(itens):
    from arquiteto_auditor.avaliacao.gabarito import Gabarito

    return Gabarito.model_validate({"conjunto": "teste", "versao_gabarito": 1, "rodada": "R00",
                                    "itens_esperados": itens})


def test_muro_aceita_item_unico_ou_um_por_posicao():
    # gabaritos antigos (sem escopo) continuam válidos: o escopo de posição é opcional
    assert _gabarito_com([{"chave": "MURO_ALTURA_MAX", "status": "atende"}])
    por_posicao = _gabarito_com([
        {"chave": "MURO_ALTURA_MAX", "escopo": "posicao=fundos", "status": "atende"},
        {"chave": "MURO_ALTURA_MAX", "escopo": "posicao=lateral", "status": "nao_atende"},
    ])
    assert len(por_posicao.erros_esperados()) == 1


def test_area_construida_minima_esta_no_catalogo():
    assert _gabarito_com([{"chave": "AREA_CONSTR_MIN", "status": "atende"}])
