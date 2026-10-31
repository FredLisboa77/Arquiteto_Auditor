"""Testes das pranchas "estilo AutoCAD" (variações calibradas com exemplos reais, docs/06 §4)."""

import dataclasses

import pymupdf
import pytest

from dados_sinteticos.geradores import fonte_shx
from dados_sinteticos.geradores.especificacao import (
    aplicar_erros,
    gerar_gabarito,
    gerar_projeto_base,
)
from dados_sinteticos.geradores.pranchas import MARCA_FICTICIO, gerar_pdfs

CAD = {"estilo_quadro": 4, "estilo_norte": "rosa_girada", "decimal_ponto": True,
       "cotas_rotuladas": False, "codigos_cad": True, "notacao_cad": True,
       "vizinhos_com_area": True, "arquivo_unico": True, "estilo_carimbo": 0, "formato": "A2"}


def _pranchas(erros=(), **variacao):
    projeto = aplicar_erros(gerar_projeto_base(111), list(erros))
    projeto.variacao = dataclasses.replace(projeto.variacao, **(CAD | variacao))
    (_, pdf), = gerar_pdfs(projeto)
    return projeto, pymupdf.open(stream=pdf)


def _comentarios(pagina) -> list[str]:
    return [a.info["content"] for a in pagina.annots()]


# ---------------------------------------------------------------- fonte de traços


def test_fonte_shx_tem_todos_os_caracteres_usados_nas_pranchas():
    usados = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:-—_/()=+%²³º'\"!?&"
    assert all(c in fonte_shx.GLIFOS for c in usados)
    assert fonte_shx.normalizar("Área de projeção m²") == "AREA DE PROJECAO M²"
    assert fonte_shx.largura("AB") < fonte_shx.largura("ABC")
    assert fonte_shx.tracos(" ") == []
    for traco in fonte_shx.tracos("TO=40.00%"):  # só segmentos de reta (como o SHX)
        assert len(traco) >= 2


# ---------------------------------------------------------------- texto SHX + comentários


def test_modo_shx_nao_tem_texto_selecionavel_alem_da_marca():
    projeto, pdf = _pranchas(texto_cad="shx")
    for pagina in pdf:
        texto = " ".join(pagina.get_text().split())
        assert texto in ("", MARCA_FICTICIO)
        assert len(pagina.get_drawings()) > 200  # o texto virou desenho
    comentarios = " ".join(_comentarios(pdf[0]))
    assert projeto.identificacao.matricula in comentarios
    assert "Escritório" in comentarios  # no modo "shx" até os rótulos viram traços


def test_modo_misto_tem_rotulos_em_texto_e_valores_so_nos_comentarios():
    projeto, pdf = _pranchas(texto_cad="misto")
    texto = " ".join(pdf[0].get_text().split())
    comentarios = _comentarios(pdf[0])
    assert "Matrícula:" in texto or "MATRÍCULA:" in texto
    assert projeto.identificacao.autor not in texto
    assert projeto.identificacao.autor in comentarios


def test_comentarios_sao_invisiveis_e_tem_codigos_do_autocad():
    projeto, pdf = _pranchas(texto_cad="misto")
    tipos = [(a.type[1], a.opacity) for a in pdf[0].annots()]  # ler durante a iteração
    assert tipos and set(tipos) == {("Square", 0)}
    comentarios = _comentarios(pdf[0])
    assert f"{projeto.to_prancha:.2f}%%%" in comentarios  # "%" gravado como "%%%"
    assert f"C={projeto.ca_prancha:.2f}" in comentarios
    assert ["TAXA DE", "OCUPAÇÃO"] == [c for c in comentarios if c in ("TAXA DE", "OCUPAÇÃO")][:2]


def test_altura_e_muro_na_notacao_do_autocad():
    projeto, pdf = _pranchas(texto_cad="misto")
    todos = [c for pagina in pdf for c in _comentarios(pagina)]
    assert f"H={projeto.edificacao.altura:.2f}m" in todos
    assert f"MURO H={projeto.edificacao.muro_altura:.2f}m" in todos
    _, sem_altura = _pranchas(["cota_omitida:altura_total", "cota_omitida:muro"],
                              texto_cad="misto")
    todos = [c for pagina in sem_altura for c in _comentarios(pagina)]
    assert not any(c.startswith(("H=", "MURO H=")) for c in todos)


def test_lotes_vizinhos_com_area_e_rosa_girada_com_e():
    projeto, pdf = _pranchas(texto_cad="misto")
    comentarios = _comentarios(pdf[0])
    areas = [c for c in comentarios if c.endswith(" m²")]
    assert f"{projeto.area_terreno_prancha:.2f} m²" in areas
    assert len(set(areas)) >= 4  # outras áreas: distração para TERRENO_AREA
    assert "E" in comentarios and "L" not in comentarios


# ---------------------------------------------------------------- folhas extras e carimbo


def test_capa_e_perspectiva_sem_texto():
    projeto, pdf = _pranchas(texto_cad="ttf", capa=True, perspectiva=True)
    assert pdf.page_count == 5
    capa = " ".join(pdf[0].get_text().split())
    assert projeto.identificacao.titulo in capa and projeto.matricula_prancha in capa
    perspectiva = pdf[-1]
    assert perspectiva.get_text().strip() == "" and not list(perspectiva.annots())
    assert len(perspectiva.get_drawings()) > 10


def test_folha_empilhada_e_numeracao_com_capa():
    _, pdf = _pranchas(texto_cad="ttf", capa=True, perspectiva=True, folha_empilhada=True)
    texto = pdf[1].get_text().split()  # 1ª folha técnica = folha 02 de 05
    assert "02" in texto and "05" in texto
    assert "02/05" not in " ".join(texto)


@pytest.mark.parametrize("estilo_carimbo", [0, 3])
def test_revisao_em_branco(estilo_carimbo):
    projeto, pdf = _pranchas(texto_cad="ttf", revisao_em_branco=True,
                             estilo_carimbo=estilo_carimbo)
    assert "R00" not in " ".join(p.get_text() for p in pdf)
    item = next(i for i in gerar_gabarito(projeto, "x").itens_esperados
                if i.chave == "ID_REVISAO")
    assert item.status == "nao_verificavel"


def test_pranchas_cad_tem_bytes_reprodutiveis():
    projeto, _ = _pranchas(texto_cad="misto", capa=True)
    assert gerar_pdfs(projeto) == gerar_pdfs(projeto)
