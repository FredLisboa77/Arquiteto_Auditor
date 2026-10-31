"""Testes da escritura fictícia: coerência com a matrícula, privacidade e PDF escaneado."""

import re

import pymupdf
import pytest

from dados_sinteticos.geradores.escritura import (
    ESTILO_ESCRITURA,
    gerar_escritura,
    gerar_escritura_escaneada,
    paginas_da_escritura,
    paragrafos_da_escritura,
)
from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.registro import br, gerar_matricula
from scripts.verificar_vazamento import PADRAO_CPF, cpf_valido

SEMENTES = range(101, 113)


def _montar(semente):
    projeto = gerar_projeto_base(semente)
    matricula = gerar_matricula(projeto)
    escritura = gerar_escritura(projeto, matricula)
    texto = "\n".join(paragrafos_da_escritura(escritura, projeto, matricula))
    return projeto, matricula, escritura, texto


@pytest.mark.parametrize("semente", SEMENTES)
def test_escritura_coerente_com_o_registro_da_venda(semente):
    projeto, matricula, escritura, texto = _montar(semente)
    venda = escritura.venda
    assert venda is matricula.vendas[-1]
    assert venda.comprador.nome == projeto.identificacao.proprietario
    ato = next(a for a in matricula.atos if a.codigo == venda.codigo_ato)
    # o registro na matrícula cita a mesma escritura (livro, folhas, valor, comprador e CPF)
    for trecho in (f"livro {venda.livro}", f"folhas {venda.folhas}", br(venda.valor),
                   venda.comprador.nome, venda.comprador.documento):
        assert trecho in ato.texto
    for trecho in (venda.vendedor.nome, venda.vendedor.documento, venda.comprador.documento,
                   f"R$ {br(venda.valor)}", matricula.numero, f"{br(venda.area)} m²"):
        assert trecho in texto
    assert ato.data > venda.data_escritura  # registra-se depois de lavrar


def test_escritura_pode_trazer_area_anterior_a_retificacao():
    """Venda antes da retificação: a escritura tem a área antiga; a matrícula, a atual."""
    casos = [_montar(s) for s in SEMENTES]
    armadilhas = [m for _, m, e, _ in casos if e.venda.area != m.area_atual]
    assert armadilhas, "nenhuma semente gerou a armadilha da área antiga"
    for _, m, e, texto in casos:
        if e.venda.area != m.area_atual:
            assert f"{br(m.area_atual)} m²" not in texto


@pytest.mark.parametrize("semente", SEMENTES)
def test_escritura_nao_contem_cpf_valido(semente):
    *_, texto = _montar(semente)
    cpfs = PADRAO_CPF.findall(texto)
    assert cpfs
    assert not any(cpf_valido("".join(c)) for c in cpfs)


def test_paginas_da_escritura_tem_os_elementos_do_cartorio():
    projeto, matricula, escritura, _ = _montar(102)
    paginas = paginas_da_escritura(escritura, projeto, matricula)
    primeira, ultima = paginas[0], paginas[-1]
    assert primeira.faixa_topo and len(primeira.molduras) == 2
    for inicio, fim in primeira.molduras:
        assert all(linha.negrito for linha in primeira.linhas[inicio:fim])
    assert "ESCRITURA PÚBLICA DE COMPRA E VENDA" in primeira.texto
    assert all(p.rubrica_margem for p in paginas)
    assert {p.cor_papel for p in paginas} <= {"branco", "amarelado"}
    assert ultima.assinaturas == 3 and ultima.selo == escritura.selo and ultima.carimbos
    assert all("DOCUMENTO FICTÍCIO" in p.texto for p in paginas)


@pytest.mark.parametrize("qualidade", ["boa", "ruim"])
def test_pdf_da_escritura_so_tem_imagem(qualidade):
    _, doc = gerar_escritura_escaneada(gerar_projeto_base(104), qualidade)
    pdf = pymupdf.open(stream=doc.pdf)
    assert pdf.page_count == len(doc.texto_por_pagina) >= 2
    for pagina in pdf:
        assert pagina.get_text().strip() == ""
        assert (pagina.rect.width, pagina.rect.height) == ESTILO_ESCRITURA.tamanho_pt
    assert len(doc.pdf) < 4 * 1024 * 1024
    assert re.search(r"SAIBAM quantos", doc.texto_por_pagina[0])
