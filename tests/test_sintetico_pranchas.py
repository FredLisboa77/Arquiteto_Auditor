"""Testes do desenho das pranchas sintéticas (lidas de volta com PyMuPDF)."""

import dataclasses

import pymupdf
import pytest

from dados_sinteticos.geradores.especificacao import aplicar_erros, gerar_projeto_base
from dados_sinteticos.geradores.pranchas import (
    LARGURA_CARIMBO,
    TAMANHOS_MM,
    desenhar_pranchas,
    formatar_numero,
)

MM = 72 / 25.4


def projeto_com(semente=1, erros=(), **variacao):
    projeto = aplicar_erros(gerar_projeto_base(semente), list(erros))
    projeto.variacao = dataclasses.replace(projeto.variacao, **variacao)
    return projeto


def paginas(caminhos):
    resultado = []
    for caminho in caminhos:
        documento = pymupdf.open(caminho)
        resultado.extend(documento)
    return resultado


def texto_de(pagina) -> str:
    return pagina.get_text()


def palavras_de(pagina) -> list[str]:
    return [p[4] for p in pagina.get_text("words")]


# ---------------------------------------------------------------- formatação


@pytest.mark.parametrize(
    ("valor", "ponto", "esperado"),
    [(450.0, False, "450,00"), (1234.5, False, "1.234,50"), (5.0, True, "5.00"),
     (1234.5, True, "1234.50")],
)
def test_formatar_numero(valor, ponto, esperado):
    assert formatar_numero(valor, decimal_ponto=ponto) == esperado


# ---------------------------------------------------------------- arquivos e páginas


def test_arquivo_unico_tem_todas_as_folhas(tmp_path):
    caminhos = desenhar_pranchas(projeto_com(arquivo_unico=True), tmp_path)
    assert len(caminhos) == 1
    assert len(paginas(caminhos)) == 3


def test_um_arquivo_por_folha(tmp_path):
    caminhos = desenhar_pranchas(projeto_com(arquivo_unico=False), tmp_path)
    assert len(caminhos) == 3
    assert all(len(pymupdf.open(c)) == 1 for c in caminhos)


@pytest.mark.parametrize("formato", ["A1", "A2", "A3"])
def test_tamanho_da_folha_em_paisagem(tmp_path, formato):
    (pagina, *_) = paginas(desenhar_pranchas(projeto_com(formato=formato), tmp_path))
    largura, altura = TAMANHOS_MM[formato]
    assert pagina.rect.width == pytest.approx(largura * MM, abs=1)
    assert pagina.rect.height == pytest.approx(altura * MM, abs=1)


def test_desenho_e_deterministico(tmp_path):
    projeto = projeto_com(arquivo_unico=True)
    (a,) = desenhar_pranchas(projeto, tmp_path / "a")
    (b,) = desenhar_pranchas(projeto, tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()


# ---------------------------------------------------------------- conteúdo


def test_texto_selecionavel_com_acentos_e_marca_de_ficticio(tmp_path):
    projeto = projeto_com(caixa_alta=True)
    texto = " ".join(texto_de(p) for p in paginas(desenhar_pranchas(projeto, tmp_path)))
    assert "ÁREA" in texto
    assert "m²" in texto
    assert "FICTÍCIO" in texto
    assert projeto.identificacao.titulo in texto


def test_metadados_identificam_documento_sintetico(tmp_path):
    (caminho, *_) = desenhar_pranchas(projeto_com(), tmp_path)
    assert "SINTÉTICO" in pymupdf.open(caminho).metadata["subject"]


@pytest.mark.parametrize("estilo_carimbo", range(4))
@pytest.mark.parametrize("estilo_quadro", range(4))
def test_todos_os_estilos_mostram_os_dados_essenciais(tmp_path, estilo_carimbo, estilo_quadro):
    projeto = projeto_com(estilo_carimbo=estilo_carimbo, estilo_quadro=estilo_quadro,
                          decimal_ponto=False)
    folhas = paginas(desenhar_pranchas(projeto, tmp_path))
    situacao = texto_de(folhas[0])
    ident = projeto.identificacao
    for esperado in (ident.titulo, ident.autor, ident.registro_autor, ident.matricula,
                     ident.proprietario, ident.revisao, ident.rrt,
                     formatar_numero(projeto.terreno.area)):
        assert esperado in situacao, esperado


def test_quadro_mostra_area_da_prancha_com_erro(tmp_path):
    projeto = projeto_com(erros=["area_terreno_divergente"], decimal_ponto=False)
    situacao = texto_de(paginas(desenhar_pranchas(projeto, tmp_path))[0])
    assert formatar_numero(projeto.area_terreno_prancha) in situacao
    assert formatar_numero(projeto.terreno.area) not in situacao


def test_matricula_divergente_aparece_na_prancha(tmp_path):
    projeto = projeto_com(erros=["matricula_divergente"])
    situacao = texto_de(paginas(desenhar_pranchas(projeto, tmp_path))[0])
    assert projeto.matricula_prancha in situacao
    assert projeto.identificacao.matricula not in situacao


def test_revisao_divergente_aparece_so_na_segunda_folha(tmp_path):
    projeto = projeto_com(erros=["revisao_divergente"], estilo_carimbo=0)
    folhas = paginas(desenhar_pranchas(projeto, tmp_path))
    assert "R01" not in texto_de(folhas[0])
    assert "R01" in texto_de(folhas[1])


def test_norte_presente_e_ausente(tmp_path):
    com = paginas(desenhar_pranchas(projeto_com(), tmp_path / "com"))[0]
    sem = paginas(desenhar_pranchas(projeto_com(erros=["sem_norte"]), tmp_path / "sem"))[0]
    assert "N" in palavras_de(com)
    assert "N" not in palavras_de(sem)


def test_proprietario_omitido(tmp_path):
    projeto = projeto_com(erros=["sem_proprietario"])
    texto = " ".join(texto_de(p) for p in paginas(desenhar_pranchas(projeto, tmp_path)))
    assert projeto.identificacao.proprietario not in texto


def test_cota_omitida_mantem_linha_mas_tira_o_texto(tmp_path):
    base = projeto_com(cotas_rotuladas=True, caixa_alta=True)
    omitida = projeto_com(erros=["cota_omitida:recuo_fundos"], cotas_rotuladas=True,
                          caixa_alta=True)
    pagina_base = paginas(desenhar_pranchas(base, tmp_path / "base"))[0]
    pagina_omitida = paginas(desenhar_pranchas(omitida, tmp_path / "omitida"))[0]
    assert "FUNDOS" in texto_de(pagina_base)
    assert "FUNDOS" not in texto_de(pagina_omitida)
    # A linha de cota continua desenhada (dimensão "apenas gráfica")
    assert len(pagina_omitida.get_drawings()) == len(pagina_base.get_drawings())


def test_cotas_com_ponto_decimal_estilo_cad(tmp_path):
    projeto = projeto_com(decimal_ponto=True)
    situacao = texto_de(paginas(desenhar_pranchas(projeto, tmp_path))[0])
    assert formatar_numero(projeto.edificacao.recuo_frontal, decimal_ponto=True) in situacao


def test_corte_mostra_altura_e_muro(tmp_path):
    projeto = projeto_com(decimal_ponto=False)
    corte = texto_de(paginas(desenhar_pranchas(projeto, tmp_path))[2])
    assert formatar_numero(projeto.edificacao.altura) in corte
    assert formatar_numero(projeto.edificacao.muro_altura) in corte


@pytest.mark.parametrize("estilo_carimbo", [0, 3])
@pytest.mark.parametrize("formato", ["A1", "A3"])
def test_desenhos_nao_invadem_o_carimbo(tmp_path, estilo_carimbo, formato):
    projeto = projeto_com(estilo_carimbo=estilo_carimbo, formato=formato, caixa_alta=True)
    folhas = paginas(desenhar_pranchas(projeto, tmp_path))
    # Carimbo dos estilos 0 e 3, encostado na margem direita (10 mm).
    inicio_carimbo = folhas[0].rect.width - (10 + LARGURA_CARIMBO[formato]) * MM
    for folha in folhas[1:]:
        for _x0, _y0, x1, _y1, palavra, *_ in folha.get_text("words"):
            if palavra in ("SUÍTE", "DORMITÓRIO", "SALA", "JANTAR"):  # não estão no carimbo
                assert x1 < inicio_carimbo, palavra


def test_norte_em_rosa_dos_ventos(tmp_path):
    folha = paginas(desenhar_pranchas(projeto_com(estilo_norte="rosa"), tmp_path))[0]
    assert {"N", "S", "L", "O"} <= set(palavras_de(folha))


def test_area_permeavel_desenhada_repete_o_valor_do_quadro(tmp_path):
    projeto = projeto_com(decimal_ponto=False)
    folha = paginas(desenhar_pranchas(projeto, tmp_path))[0]
    assert texto_de(folha).count(formatar_numero(projeto.edificacao.area_permeavel)) >= 2


def test_passeio_tem_inclinacao_e_largura(tmp_path):
    folha = paginas(desenhar_pranchas(projeto_com(decimal_ponto=False), tmp_path))[0]
    assert "i=2%" in texto_de(folha)
    assert "2,00" in palavras_de(folha)


def test_cotas_encadeadas_respeitam_a_omissao(tmp_path):
    base = projeto_com(cotas_rotuladas=False, decimal_ponto=False)
    omitida = projeto_com(erros=["cota_omitida:recuo_fundos"], cotas_rotuladas=False,
                          decimal_ponto=False)
    valor = formatar_numero(base.recuo_fundos)
    na_base = palavras_de(paginas(desenhar_pranchas(base, tmp_path / "b"))[0]).count(valor)
    na_omitida = palavras_de(paginas(desenhar_pranchas(omitida, tmp_path / "o"))[0]).count(valor)
    assert na_base >= 2  # cota principal + cota encadeada
    assert na_omitida == 0


def test_carimbo_tem_escritorio_ficticio(tmp_path):
    projeto = projeto_com()
    folha = paginas(desenhar_pranchas(projeto, tmp_path))[0]
    assert projeto.identificacao.escritorio in texto_de(folha)


def test_carimbo_alternativo_mostra_cpf_ficticio_invalido(tmp_path):
    from scripts.verificar_vazamento import cpf_valido

    projeto = projeto_com(estilo_carimbo=3)
    cpf = projeto.identificacao.cpf_proprietario
    assert cpf in texto_de(paginas(desenhar_pranchas(projeto, tmp_path))[0])
    assert not cpf_valido(cpf.replace(".", "").replace("-", ""))


def test_caixa_mista(tmp_path):
    projeto = projeto_com(caixa_alta=False, estilo_quadro=1)
    texto = texto_de(paginas(desenhar_pranchas(projeto, tmp_path))[0])
    assert "Área" in texto
