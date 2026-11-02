"""Testes da leitura de números e unidades no formato brasileiro."""

import pytest

from arquiteto_auditor.dominio.numeros import encontrar_valores, ler_extenso, ler_valor

# ---------------------------------------------------------------- ler_valor: valor + unidade


@pytest.mark.parametrize(
    ("texto", "valor", "unidade"),
    [
        # Formato brasileiro: vírgula decimal, ponto de milhar
        ("450,00", 450.0, None),
        ("1.234,56", 1234.56, None),
        ("1.234.567,89", 1234567.89, None),
        ("0,6", 0.6, None),
        ("12", 12.0, None),
        # Áreas
        ("450,00 m²", 450.0, "m2"),
        ("450,00m²", 450.0, "m2"),
        ("450,00 m2", 450.0, "m2"),
        ("450,00 M²", 450.0, "m2"),
        ("1.234,56 m²", 1234.56, "m2"),
        ("450,30 metros quadrados", 450.3, "m2"),
        # Comprimentos
        ("5,00 m", 5.0, "m"),
        ("5,00m", 5.0, "m"),
        ("5,00 metros", 5.0, "m"),
        ("1,50 mts", 1.5, "m"),
        ("150 cm", 1.5, "m"),
        # Percentuais
        ("60%", 60.0, "%"),
        ("60 %", 60.0, "%"),
        ("62,5%", 62.5, "%"),
        # Sinal (cotas de nível)
        ("-0,15", -0.15, None),
        ("+3,20", 3.2, None),
        ("-0,15 m", -0.15, "m"),
        # Ponto decimal (comum em cotas exportadas do CAD)
        ("5.00", 5.0, None),
        ("2.5 m", 2.5, "m"),
        # Espaços nas bordas e "=" de quadro de áreas
        ("  450,00 m²  ", 450.0, "m2"),
        ("= 450,00 m²", 450.0, "m2"),
        # Moeda é reconhecida (para poder ser descartada)
        ("R$ 1.000,00", 1000.0, "R$"),
    ],
)
def test_ler_valor_formatos_brasileiros(texto, valor, unidade):
    lido = ler_valor(texto)
    assert lido is not None
    assert lido.valor == pytest.approx(valor)
    assert lido.unidade == unidade


def test_milhar_com_ponto_e_tres_digitos_e_marcado_ambiguo():
    # "1.500" pode ser mil e quinhentos ou 1,5 (ponto decimal do CAD): não decidir sozinho.
    lido = ler_valor("1.500")
    assert lido is not None
    assert lido.valor == pytest.approx(1500.0)
    assert lido.ambiguo


def test_numero_com_virgula_nao_e_ambiguo():
    assert not ler_valor("1.500,00").ambiguo
    assert not ler_valor("5,00").ambiguo


@pytest.mark.parametrize(
    "texto", ["", "   ", "abc", "ÁREA DO TERRENO", "1,50 a 2,00", "5,00 e 6,00"]
)
def test_ler_valor_rejeita_texto_que_nao_e_exatamente_um_valor(texto):
    assert ler_valor(texto) is None


def test_ler_valor_guarda_o_texto_original():
    assert ler_valor("  450,00 m² ").texto == "450,00 m²"


# ---------------------------------------------------------------- encontrar_valores: em frases


def test_encontrar_valores_em_frase_do_quadro_de_areas():
    valores = encontrar_valores("ÁREA DO TERRENO: 450,00 m² | ÁREA CONSTRUÍDA: 180,50 m²")
    assert [v.valor for v in valores] == pytest.approx([450.0, 180.5])
    assert [v.unidade for v in valores] == ["m2", "m2"]


def test_encontrar_valores_informa_posicao_no_texto():
    frase = "Recuo frontal mínimo de 5,00 m"
    (valor,) = encontrar_valores(frase)
    assert frase[valor.inicio : valor.fim] == "5,00 m"


def test_encontrar_valores_em_artigo_de_lei():
    frase = "Art. 12. A taxa de ocupação máxima na ZR-2 é de 60% (sessenta por cento)."
    valores = encontrar_valores(frase)
    percentuais = [v for v in valores if v.unidade == "%"]
    assert [v.valor for v in percentuais] == [60.0]


def test_encontrar_valores_nao_confunde_numero_da_matricula_com_area():
    valores = encontrar_valores("Matrícula nº 12.345 — área de 450,00 m²")
    areas = [v for v in valores if v.unidade == "m2"]
    assert [v.valor for v in areas] == [450.0]


def test_encontrar_valores_ignora_letras_coladas_em_codigos():
    # "ZR2" e "R-1" são códigos, não medidas
    valores = encontrar_valores("Zona ZR2, ato R-1")
    assert valores == []


def test_encontrar_valores_texto_vazio():
    assert encontrar_valores("") == []


# ---------------------------------------------------------------- ler_extenso: números por extenso


@pytest.mark.parametrize(
    ("texto", "numero"),
    [
        ("um", 1),
        ("dois", 2),
        ("duas", 2),
        ("três", 3),
        ("tres", 3),
        ("dez", 10),
        ("dezesseis", 16),
        ("vinte e um", 21),
        ("sessenta", 60),
        ("cem", 100),
        ("cento e vinte", 120),
        ("quatrocentos e cinquenta", 450),
        ("quatrocentos e cinqüenta", 450),
        ("mil", 1000),
        ("mil e duzentos", 1200),
        ("dois mil trezentos e quarenta e cinco", 2345),
        ("doze mil", 12000),
        ("Sessenta", 60),
    ],
)
def test_ler_extenso(texto, numero):
    assert ler_extenso(texto) == numero


@pytest.mark.parametrize("texto", ["", "pavimento", "dois pavimentos", "e", "mil mil"])
def test_ler_extenso_rejeita_o_que_nao_e_numero_por_extenso(texto):
    assert ler_extenso(texto) is None


def test_ler_valor_aceita_numero_com_extenso_entre_parenteses():
    lido = ler_valor("2 (dois) pavimentos")
    assert lido.valor == 2.0
    assert lido.unidade == "pavimentos"


def test_ler_valor_aceita_numero_so_por_extenso_com_unidade():
    lido = ler_valor("dois pavimentos")
    assert lido.valor == 2.0
    assert lido.unidade == "pavimentos"


def test_ler_valor_marca_divergencia_entre_numero_e_extenso():
    # Erro comum em documentos: o algarismo diz uma coisa e o extenso outra.
    lido = ler_valor("60% (cinquenta por cento)")
    assert lido.valor == 60.0
    assert lido.extenso_divergente


def test_codigos_de_controle_do_autocad():
    """docs/06 §2: o AutoCAD grava "%%%" no lugar de "%" (e %%c, %%d, %%p para ø, °, ±)."""
    lido = ler_valor("56.10%%%")
    assert lido is not None and lido.valor == 56.1 and lido.unidade == "%"
    (achado,) = encontrar_valores("TAXA 29.99%%% (máx.)")
    assert achado.valor == 29.99 and achado.unidade == "%"
    assert "TAXA 29.99%%% (máx.)"[achado.inicio:achado.inicio + 5] == "29.99"  # posição mantida


def test_numero_do_extenso_de_area():
    from arquiteto_auditor.dominio.numeros import numero_do_extenso
    assert numero_do_extenso("trezentos e setenta e cinco metros quadrados") == 375
    assert numero_do_extenso("quatrocentos e quarenta e seis metros quadrados e vinte e "
                             "cinco decímetros quadrados") == 446  # a parte inteira
    assert numero_do_extenso("trezentos e. sessenta metros quadrados") == 360  # sujeira de OCR
    assert numero_do_extenso("sem número") is None
