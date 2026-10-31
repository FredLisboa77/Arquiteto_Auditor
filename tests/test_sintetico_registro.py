"""Testes da matrícula fictícia (conteúdo) e do "scanner" fictício (imagem/PDF)."""

import random
import re

import pymupdf
import pytest

from arquiteto_auditor.dominio.numeros import ler_extenso
from dados_sinteticos.geradores.escaneado import (
    Estilo,
    Linha,
    Pagina,
    paginar,
    posicoes_das_palavras,
    quebrar,
)
from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.registro import (
    ESTILOS_MATRICULA,
    area_por_extenso,
    br,
    cnpj_invalido,
    gerar_matricula,
    gerar_matricula_escaneada,
    paginas_da_matricula,
    por_extenso,
)
from scripts.verificar_vazamento import PADRAO_CPF, cpf_valido

SEMENTES = range(101, 113)


def cnpj_valido(digitos: str) -> bool:
    numeros = [int(d) for d in digitos]
    for tamanho, pesos in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
                           (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        resto = sum(d * p for d, p in zip(numeros[:tamanho], pesos, strict=True)) % 11
        if numeros[tamanho] != (0 if resto < 2 else 11 - resto):
            return False
    return True


# ---------------------------------------------------------------- por extenso


@pytest.mark.parametrize("numero, esperado", [
    (1, "um"), (16, "dezesseis"), (100, "cem"), (101, "cento e um"),
    (366, "trezentos e sessenta e seis"), (1000, "mil"), (1100, "mil e cem"),
    (1120, "mil cento e vinte"), (2025, "dois mil e vinte e cinco"),
    (525_000, "quinhentos e vinte e cinco mil"),
])
def test_por_extenso(numero, esperado):
    assert por_extenso(numero) == esperado


def test_por_extenso_e_lido_de_volta_pelo_normalizador():
    for numero in [*range(0, 1200), *range(1200, 999_999, 7_777)]:
        assert ler_extenso(por_extenso(numero)) == numero


def test_area_por_extenso_com_decimais():
    assert area_por_extenso(450.0) == "quatrocentos e cinquenta metros quadrados"
    assert area_por_extenso(437.5) == (
        "quatrocentos e trinta e sete metros quadrados e cinquenta decímetros quadrados")


def test_cnpj_gerado_e_sempre_invalido():
    rng = random.Random(1)
    for _ in range(300):
        cnpj = cnpj_invalido(rng)
        assert re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/0001-\d{2}", cnpj)
        assert not cnpj_valido(re.sub(r"\D", "", cnpj))


# ---------------------------------------------------------------- conteúdo da matrícula


@pytest.mark.parametrize("semente", SEMENTES)
def test_matricula_mostra_a_verdade_registral(semente):
    projeto = gerar_projeto_base(semente)
    m = gerar_matricula(projeto)
    assert 2 <= len(m.atos) + 1 <= 7  # abertura + 1 a 6 atos
    assert m.numero == projeto.identificacao.matricula
    assert m.area_atual == projeto.terreno.area
    assert m.proprietario_atual == projeto.identificacao.proprietario
    # a última transmissão (R- de compra e venda) é para o proprietário atual
    vendas = [a for a in m.atos if a.titulo == "COMPRA E VENDA"]
    assert projeto.identificacao.proprietario in vendas[-1].texto
    # a área atual aparece no texto: na abertura ou na última retificação
    retificacoes = [a for a in m.atos if a.titulo == "RETIFICAÇÃO DE ÁREA"]
    descricao_vigente = retificacoes[-1].texto if retificacoes else m.abertura
    assert f"{br(m.area_atual)} m²" in descricao_vigente
    if retificacoes:
        assert f"{br(m.area_atual)} m²" not in m.abertura  # a abertura tem a área antiga
    datas = [m.data_abertura, *(a.data for a in m.atos)]
    assert datas == sorted(datas)


def test_base_de_sementes_cobre_as_variacoes_de_atos():
    titulos = [{a.titulo for a in gerar_matricula(gerar_projeto_base(s)).atos} for s in SEMENTES]
    assert any("RETIFICAÇÃO DE ÁREA" in t for t in titulos)
    assert any("RETIFICAÇÃO DE ÁREA" not in t for t in titulos)
    assert any("CANCELAMENTO" in t for t in titulos)
    assert any(sum(1 for _ in t) >= 3 for t in titulos)


@pytest.mark.parametrize("semente", SEMENTES)
def test_matricula_nao_contem_cpf_nem_cnpj_validos(semente):
    m = gerar_matricula(gerar_projeto_base(semente))
    texto = "\n".join(m.paragrafos())
    cpfs = PADRAO_CPF.findall(texto)
    assert cpfs, "a matrícula fictícia deveria qualificar as partes com CPF"
    assert not any(cpf_valido("".join(c)) for c in cpfs)
    for cnpj in re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto):
        assert not cnpj_valido(re.sub(r"\D", "", cnpj))


def test_matricula_e_deterministica():
    projeto = gerar_projeto_base(104)
    assert gerar_matricula(projeto).paragrafos() == gerar_matricula(projeto).paragrafos()
    assert gerar_matricula(projeto, 1).paragrafos() != gerar_matricula(projeto).paragrafos()


# ---------------------------------------------------------------- diagramação


ESTILOS = [Estilo(), Estilo(fonte="times", formato="carta"), Estilo(fonte="arial")]


@pytest.mark.parametrize("estilo", ESTILOS, ids=lambda e: e.fonte)
def test_linhas_justificadas_ocupam_a_largura_toda(estilo):
    linhas = quebrar("palavra comprida " * 60, estilo, prefixo_negrito=7)
    assert len(linhas) > 3
    for linha in linhas[:-1]:
        x, palavra, negrito = posicoes_das_palavras(linha, estilo)[-1]
        fim = x + estilo.medir(palavra, negrito)
        assert fim == pytest.approx(estilo.largura_texto_pt, abs=0.5)
    ultima = posicoes_das_palavras(linhas[-1], estilo)
    assert ultima[-1][0] + estilo.medir(ultima[-1][1]) < estilo.largura_texto_pt


def test_rotulo_em_negrito_so_no_inicio_do_paragrafo():
    linhas = quebrar("R-1/81.735 - Em 08 de abril de 2012. COMPRA E VENDA: texto " * 5,
                     Estilo(fonte="times"), recuo=0, prefixo_negrito=10)
    negritos = [palavra for _, palavra, negrito in posicoes_das_palavras(linhas[0], Estilo())
                if negrito]
    assert negritos == ["R-1/81.735"]
    assert not any(n for linha in linhas[1:] for *_, n in posicoes_das_palavras(linha, Estilo()))


def test_linha_alinhada_a_esquerda_respeita_colunas():
    estilo = Estilo()  # máquina de escrever: cada caractere tem a mesma largura
    linha = Linha("MATRÍCULA Nº 1.234" + " " * 10 + "FICHA 01")
    posicoes = posicoes_das_palavras(linha, estilo)
    assert posicoes[-2][1] == "FICHA"
    assert posicoes[-2][0] == pytest.approx(estilo.medir("x" * 28))


def test_verdade_do_ocr_tem_espacos_simples_e_ignora_o_brasao():
    linhas = [Linha("", brasao=True, escala=3), Linha("A   B", "justificado"), Linha("")]
    assert Pagina(linhas).texto == "A B"


def test_paginar_respeita_limite_e_reserva_final():
    estilo = Estilo()
    blocos = [quebrar("texto de exemplo " * 40, estilo) for _ in range(6)]
    paginas = paginar(blocos, lambda n: [Linha(f"CABEÇALHO {n}", escala=2)], estilo,
                      reserva_final=14)
    limite = estilo.linhas_por_pagina
    assert len(paginas) >= 2
    assert all(sum(linha.escala for linha in p.linhas) <= limite for p in paginas)
    assert sum(linha.escala for linha in paginas[-1].linhas) <= limite - 14
    assert [p.linhas[0].texto for p in paginas] == [f"CABEÇALHO {n}"
                                                    for n in range(1, len(paginas) + 1)]


def test_ficha_antiga_tem_certidao_selo_e_aviso_de_ficticio():
    m = gerar_matricula(gerar_projeto_base(102))
    paginas = paginas_da_matricula(m, semente=1, estilo="ficha")
    assert all("DOCUMENTO FICTÍCIO" in p.texto for p in paginas)
    assert "CERTIDÃO" in paginas[-1].texto
    assert paginas[-1].selo and paginas[-1].carimbos and paginas[-1].assinaturas
    assert all(len(p.molduras) == 1 and p.molduras[0][0] == 0 for p in paginas)  # cabeçalho


def test_certidao_moderna_tem_frente_e_verso_e_carimbos_copia():
    m = gerar_matricula(gerar_projeto_base(102))
    paginas = paginas_da_matricula(m, semente=1, estilo="certidao")
    assert len(paginas) % 2 == 0  # folhas inteiras: frente e verso
    assert [p.verso for p in paginas] == [i % 2 == 1 for i in range(len(paginas))]
    assert all(p.copias > 0 for p in paginas)
    assert "CERTIDÃO DE INTEIRO TEOR" in paginas[0].texto
    assert "REPÚBLICA FEDERATIVA DO BRASIL" in paginas[0].texto
    com_texto = [p for p in paginas if p.linhas]
    assert com_texto[-1].selo and com_texto[-1].anular_espaco
    # a verdade do OCR não inclui o carimbo "CÓPIA"
    assert not any("CÓPIA" in p.texto for p in paginas)


# ---------------------------------------------------------------- PDF escaneado


@pytest.mark.parametrize("qualidade", ["boa", "media", "ruim"])
@pytest.mark.parametrize("estilo", ["ficha", "certidao"])
def test_pdf_escaneado_so_tem_imagem(qualidade, estilo):
    _, doc = gerar_matricula_escaneada(gerar_projeto_base(103), qualidade, estilo=estilo)
    pdf = pymupdf.open(stream=doc.pdf)
    assert pdf.page_count == len(doc.texto_por_pagina)
    largura, altura = ESTILOS_MATRICULA[estilo].tamanho_pt
    for pagina in pdf:
        assert pagina.get_text().strip() == ""  # sem camada de texto, como um scanner
        assert len(pagina.get_images()) == 1
        assert (pagina.rect.width, pagina.rect.height) == (largura, altura)
    assert len(doc.pdf) < 4 * 1024 * 1024  # abaixo do limite de 5 MB do anti-vazamento
