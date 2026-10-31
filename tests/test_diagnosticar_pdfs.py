"""Testes do diagnóstico de PDFs (roda sobre documentos reais mostrando só estatísticas)."""

import pymupdf
import pytest

from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.pranchas import desenhar_pranchas
from scripts.diagnosticar_pdfs import diagnosticar_pasta, formatar_relatorio, software_produtor


@pytest.fixture(scope="module")
def pasta_com_pdfs(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("pdfs")
    projeto = gerar_projeto_base(11)
    desenhar_pranchas(projeto, pasta)
    (pasta / "nao_e_pdf.pdf").write_bytes(b"isto nao e um pdf")
    return pasta, projeto


def test_estatisticas_basicas(pasta_com_pdfs):
    pasta, _ = pasta_com_pdfs
    arquivos = diagnosticar_pasta(pasta)
    validos = [a for a in arquivos if a["erro"] is None]
    assert sum(a["paginas"] for a in validos) == 3
    pagina = validos[0]["por_pagina"][0]
    assert pagina["caracteres"] > 100
    assert pagina["desenhos"] > 0
    assert pagina["valores_com_unidade"] > 0
    assert not pagina["suspeita_texto_como_desenho"]
    assert not pagina["suspeita_escaneada"]


def test_medidas_para_detectar_cotas_como_desenho(pasta_com_pdfs):
    pasta, _ = pasta_com_pdfs
    validos = [a for a in diagnosticar_pasta(pasta) if a["erro"] is None]
    pagina = validos[0]["por_pagina"][0]
    assert pagina["palavras_numericas"] > 5  # cotas e quadro de áreas como texto
    assert 0 < pagina["ocupacao_texto"] <= 1  # fração da folha (grade 10×10) que tem texto
    assert pagina["anotacoes"] == 0  # comentários do PDF (o AutoCAD pode pôr o texto SHX aqui)
    assert pagina["tracos_pequenos"] >= 0  # traços do tamanho de uma letra


def test_conta_texto_guardado_em_comentarios_sem_mostrar_o_conteudo(tmp_path):
    # O AutoCAD pode guardar o texto SHX em comentários invisíveis do PDF.
    documento = pymupdf.open()
    pagina = documento.new_page()
    for i, conteudo in enumerate(("RECUO FRONTAL", "5,00", "12.345", "")):
        anotacao = pagina.add_rect_annot(pymupdf.Rect(50, 50 + 30 * i, 120, 70 + 30 * i))
        anotacao.set_info(content=conteudo)
        anotacao.update()
    documento.save(tmp_path / "comentarios.pdf")

    (arquivo,) = diagnosticar_pasta(tmp_path)
    estatisticas = arquivo["por_pagina"][0]
    assert estatisticas["anotacoes"] == 4
    assert estatisticas["anotacoes_com_texto"] == 3
    assert estatisticas["numeros_em_anotacoes"] == 2
    relatorio = formatar_relatorio([arquivo])
    assert "RECUO" not in relatorio
    assert "12.345" not in relatorio


def test_arquivo_invalido_nao_interrompe(pasta_com_pdfs):
    pasta, _ = pasta_com_pdfs
    arquivos = diagnosticar_pasta(pasta)
    assert any(a["erro"] for a in arquivos)


def test_relatorio_nao_expoe_conteudo_nem_nomes_de_arquivo(pasta_com_pdfs):
    pasta, projeto = pasta_com_pdfs
    relatorio = formatar_relatorio(diagnosticar_pasta(pasta))
    ident = projeto.identificacao
    for proibido in (ident.titulo, ident.autor, ident.proprietario, ident.matricula,
                     ident.endereco, "prancha_01", "pranchas.pdf", "nao_e_pdf"):
        assert proibido not in relatorio, proibido
    assert "arquivo 1" in relatorio


@pytest.mark.parametrize(
    ("produtor", "esperado"),
    [("AutoCAD 2024 - English 2024 (24.3s)", "AutoCAD"),
     ("Autodesk Revit 2023", "Revit"),
     ("C:\\Users\\Fulano\\Desktop\\projeto.dwg", "outro"),
     ("Gerador sintético Arquiteto Auditor (estilo revit)", "base sintética"),
     ("", "não informado")],
)
def test_software_produtor_so_mostra_nomes_conhecidos(produtor, esperado):
    assert software_produtor(produtor) == esperado
