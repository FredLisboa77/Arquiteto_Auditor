"""Testes do mascaramento de PDFs reais (mostra o layout, esconde dados pessoais)."""

import re

import pymupdf
import pytest

from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.pranchas import desenhar_pranchas
from scripts.mascarar_pdf import mascarar_documento, mascarar_texto, mascarar_token


@pytest.mark.parametrize(
    ("token", "esperado"),
    [
        # Vocabulário técnico: aparece como está (com ou sem acento, pontuação, caixa)
        ("RECUO", "RECUO"), ("Recuo", "Recuo"), ("ÁREA", "ÁREA"), ("área:", "área:"),
        ("TERRENO", "TERRENO"), ("PERMEÁVEL", "PERMEÁVEL"), ("m²", "m²"), ("%", "%"),
        ("de", "de"), ("N", "N"), ("1º", "1º"), ("2ª", "2ª"), ("ESQ.", "ESQ."),
        ("D'ÁGUA", "D'ÁGUA"),
        # Medidas: aparecem como estão
        ("5,00", "5,00"), ("450,00", "450,00"), ("1.234,56", "1.234,56"), ("12.50", "12.50"),
        ("+3,02", "+3,02"), ("450,00m²", "450,00m²"), ("60%", "60%"), ("12", "12"),
        ("i=2%", "i=2%"),
        # Palavras desconhecidas (nomes, ruas, escritórios): só o formato
        ("Silva", "Xxxxx"), ("JOSÉ", "XXXX"), ("Palmeiras,", "Xxxxxxxxx,"),
        # Identificadores: dígitos mascarados
        ("12.345", "99.999"), ("15/09/2026", "99/99/9999"), ("A123456-7", "X999999-9"),
        ("16344038", "99999999"), ("2026", "9999"), ("(11)", "(11)"),
    ],
)
def test_mascarar_token(token, esperado):
    assert mascarar_token(token) == esperado


def test_cpf_e_mascarado_mesmo_com_digitos_validos():
    # CPF de exemplo público, montado em partes para não disparar a verificação anti-vazamento
    cpf = "529.982.247" + "-25"
    assert mascarar_texto(f"CPF {cpf}") == "CPF 999.999.999-99"


def test_mascarar_texto_preserva_espacos_e_ordem():
    assert mascarar_texto("ÁREA DO TERRENO: 450,00 m²") == "ÁREA DO TERRENO: 450,00 m²"
    assert mascarar_texto("Proprietário: Maria Souza") == "Proprietário: Xxxxx Xxxxx"


@pytest.fixture(scope="module")
def prancha(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("prancha")
    projeto = gerar_projeto_base(21)
    (caminho, *_) = desenhar_pranchas(projeto, pasta)
    documento = pymupdf.open(caminho)
    pagina = documento[0]
    anotacao = pagina.add_rect_annot(pymupdf.Rect(40, 40, 90, 60))
    anotacao.set_info(content=f"MATRÍCULA {projeto.identificacao.matricula} RECUO 5,00")
    anotacao.update()
    com_comentario = pasta / "com_comentario.pdf"
    documento.save(com_comentario)
    return com_comentario, projeto


def test_documento_mascarado_mostra_layout_e_termos_tecnicos(prancha):
    caminho, _ = prancha
    saida = mascarar_documento(caminho)
    assert "QUADRO DE ÁREAS" in saida.upper()
    assert "RECUO" in saida.upper()
    assert "mm" in saida  # posições em milímetros


def test_documento_mascarado_nao_tem_dados_pessoais(prancha):
    caminho, projeto = prancha
    saida = mascarar_documento(caminho)
    ident = projeto.identificacao
    for proibido in (ident.autor, ident.proprietario, ident.matricula, ident.rrt,
                     ident.registro_autor, ident.escritorio, ident.cpf_proprietario,
                     ident.titulo, ident.condominio, ident.municipio,
                     ident.endereco.split(",")[0], caminho.name):
        assert proibido not in saida, proibido
    for parte in ident.autor.split() + ident.proprietario.split():
        if len(parte) > 2:  # partículas como "da" e "dos" aparecem em qualquer texto
            assert not re.search(rf"{re.escape(parte)}", saida), parte


def test_comentarios_sao_mascarados(prancha):
    caminho, projeto = prancha
    saida = mascarar_documento(caminho)
    assert "comentário" in saida
    assert "RECUO 5,00" in saida
    assert projeto.identificacao.matricula not in saida
