"""Testes da assinatura digital fictícia das pranchas sintéticas."""

import io

import pytest
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from dados_sinteticos.geradores.assinatura import Assinante, assinar_pdf
from dados_sinteticos.geradores.especificacao import gerar_projeto_base
from dados_sinteticos.geradores.pranchas import gerar_pdfs


@pytest.fixture(scope="module")
def pdf_sem_assinatura() -> bytes:
    (_, conteudo), *_ = gerar_pdfs(gerar_projeto_base(1))
    return conteudo


@pytest.fixture(scope="module")
def assinantes():
    return Assinante.criar("AUTOR FICTICIO"), Assinante.criar("PROPRIETARIO FICTICIO")


def assinaturas(conteudo: bytes):
    # Confia só nos certificados fictícios gerados nos testes (nada de lista do sistema).
    leitor = PdfFileReader(io.BytesIO(conteudo))
    resultado = []
    for assinatura in leitor.embedded_signatures:
        contexto = ValidationContext(trust_roots=[assinatura.signer_cert], allow_fetching=False)
        resultado.append((assinatura.field_name, validate_pdf_signature(assinatura, contexto)))
    return resultado


def test_assinatura_do_autor_e_do_proprietario(pdf_sem_assinatura, assinantes):
    autor, proprietario = assinantes
    assinado = assinar_pdf(pdf_sem_assinatura, autor=autor, proprietario=proprietario)
    resultado = assinaturas(assinado)
    assert [nome for nome, _ in resultado] == ["AssinaturaAutor", "AssinaturaProprietario"]
    assert all(status.intact for _, status in resultado)


def test_sem_assinatura_do_proprietario(pdf_sem_assinatura, assinantes):
    assinado = assinar_pdf(pdf_sem_assinatura, autor=assinantes[0], proprietario=None)
    assert [nome for nome, _ in assinaturas(assinado)] == ["AssinaturaAutor"]


def test_sem_nenhuma_assinatura_devolve_o_pdf_original(pdf_sem_assinatura):
    assert assinar_pdf(pdf_sem_assinatura, autor=None, proprietario=None) == pdf_sem_assinatura


def test_alteracao_apos_assinar_quebra_a_integridade(pdf_sem_assinatura, assinantes):
    autor, proprietario = assinantes
    alterado = assinar_pdf(pdf_sem_assinatura, autor=autor, proprietario=proprietario,
                           alterar_depois=True)
    resultado = assinaturas(alterado)
    assert resultado  # as assinaturas continuam lá...
    assert not any(status.intact for _, status in resultado)  # ...mas não conferem mais


def test_titular_do_certificado(pdf_sem_assinatura, assinantes):
    assinado = assinar_pdf(pdf_sem_assinatura, autor=assinantes[0], proprietario=None)
    (_, status), = assinaturas(assinado)
    assert "AUTOR FICTICIO" in status.signing_cert.subject.human_friendly
