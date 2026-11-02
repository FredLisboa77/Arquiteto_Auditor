"""Testes da leitura das assinaturas digitais (pyHanko, offline, certificados fictícios)."""

import io

import pymupdf
import pytest
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

from arquiteto_auditor.ingestao.assinaturas import ler_assinaturas, nome_do_titular
from dados_sinteticos.geradores.assinatura import Assinante, assinar_pdf


@pytest.fixture(scope="module")
def assinantes():
    return Assinante.criar("Ana Autora Fictícia"), Assinante.criar("Paulo Proprietário Fictício")


def _pdf() -> bytes:
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), "PRANCHA FICTÍCIA")
    return documento.tobytes()


def test_assinaturas_integras(tmp_path, assinantes):
    caminho = tmp_path / "prancha.pdf"
    caminho.write_bytes(assinar_pdf(_pdf(), *assinantes))
    autor, proprietario = ler_assinaturas(caminho)
    assert autor.campo == "AssinaturaAutor" and autor.titular == "Ana Autora Fictícia"
    assert proprietario.titular == "Paulo Proprietário Fictício"
    assert autor.integra and proprietario.integra
    assert proprietario.cobre_arquivo_inteiro  # a última assinatura cobre tudo
    assert not autor.confiavel  # certificado fictício: sem cadeia de confiança


def test_documento_alterado_depois_de_assinado(tmp_path, assinantes):
    conteudo = assinar_pdf(_pdf(), *assinantes)
    posicao = conteudo.find(b"PRANCHA")  # muda um byte coberto pela assinatura
    alterado = conteudo[:posicao] + b"X" + conteudo[posicao + 1:] if posicao > 0 else None
    if alterado is None:  # o texto pode estar comprimido: muda o cabeçalho
        alterado = conteudo[:5] + b"9" + conteudo[6:]
    caminho = tmp_path / "prancha.pdf"
    caminho.write_bytes(alterado)
    assert not any(a.integra for a in ler_assinaturas(caminho))


def test_alteracao_salva_depois_da_assinatura_nao_fica_coberta(tmp_path, assinantes):
    assinado = assinar_pdf(_pdf(), assinantes[0], None)
    escritor = IncrementalPdfFileWriter(io.BytesIO(assinado))
    escritor.root["/Lang"] = generic.pdf_string("pt-BR")  # qualquer mudança salva depois
    escritor.update_root()
    saida = io.BytesIO()
    escritor.write(saida)
    caminho = tmp_path / "prancha.pdf"
    caminho.write_bytes(saida.getvalue())
    (autor,) = ler_assinaturas(caminho)
    assert autor.integra and not autor.cobre_arquivo_inteiro


def test_pdf_sem_assinatura(tmp_path):
    caminho = tmp_path / "prancha.pdf"
    caminho.write_bytes(_pdf())
    assert ler_assinaturas(caminho) == []


@pytest.mark.parametrize("cn, nome", [
    ("ANA AUTORA FICTICIA:12345678900", "ANA AUTORA FICTICIA"),  # e-CPF da ICP-Brasil
    ("Ana Autora", "Ana Autora"),
    (None, None),
])
def test_nome_do_titular_nunca_traz_cpf(cn, nome):
    assert nome_do_titular(cn) == nome
