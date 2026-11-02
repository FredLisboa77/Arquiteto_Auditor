"""Testes da leitura de datas em documentos brasileiros."""

from datetime import date

import pytest

from arquiteto_auditor.dominio.datas import encontrar_data, ler_data


@pytest.mark.parametrize("texto, esperado", [
    ("21 de março de 2010", date(2010, 3, 21)),
    ("1º de janeiro de 2015", date(2015, 1, 1)),
    ("03 de Abril de 2016", date(2016, 4, 3)),
    ("21/03/2010", date(2010, 3, 21)),
    ("21.03.2010", date(2010, 3, 21)),
    ("'03 de abril de 2016", date(2016, 4, 3)),  # sujeira de OCR antes do número
    ("08 de fevereiro de. 2010", date(2010, 2, 8)),
    ("30 de fevereiro de 2010", None),  # data impossível
    ("sem data nenhuma", None),
])
def test_ler_data(texto, esperado):
    assert ler_data(texto) == esperado


def test_encontrar_data_devolve_a_primeira_com_posicao():
    texto = "R-1/81.735 - Em 30 de outubro de 2015. COMPRA E VENDA: lavrada em 13 de março de 2014"
    data, inicio, fim = encontrar_data(texto)
    assert data == date(2015, 10, 30) and texto[inicio:fim].startswith("30 de outubro")
    assert encontrar_data("nada") is None
