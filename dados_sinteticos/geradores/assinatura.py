"""Assinatura digital FICTÍCIA das pranchas sintéticas (certificados autoassinados).

Simula os três casos do gabarito real: assinatura presente e íntegra, assinatura ausente e
documento alterado depois de assinado (integridade quebrada). Os certificados são gerados na
hora, não valem para nada fora dos testes e não correspondem a nenhuma pessoa real.
"""

from __future__ import annotations

import datetime
import io
from dataclasses import dataclass

from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko_certvalidator.registry import SimpleCertificateStore

_VALIDADE_INICIO = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


@dataclass(frozen=True)
class Assinante:
    nome: str
    assinador: signers.SimpleSigner

    @classmethod
    def criar(cls, nome: str) -> Assinante:
        chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        sujeito = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, nome),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BASE SINTETICA - CERTIFICADO FICTICIO"),
        ])
        certificado = (
            x509.CertificateBuilder()
            .subject_name(sujeito)
            .issuer_name(sujeito)
            .public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_VALIDADE_INICIO)
            .not_valid_after(_VALIDADE_INICIO + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(chave, hashes.SHA256())
        )
        cert_asn1 = asn1_x509.Certificate.load(
            certificado.public_bytes(serialization.Encoding.DER))
        chave_asn1 = asn1_keys.PrivateKeyInfo.load(chave.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        assinador = signers.SimpleSigner(
            signing_cert=cert_asn1, signing_key=chave_asn1,
            cert_registry=SimpleCertificateStore.from_certs([cert_asn1]),
        )
        return cls(nome=nome, assinador=assinador)


def _assinar(conteudo: bytes, assinante: Assinante, campo: str) -> bytes:
    escritor = IncrementalPdfFileWriter(io.BytesIO(conteudo))
    metadados = signers.PdfSignatureMetadata(field_name=campo, reason="Documento fictício")
    return signers.sign_pdf(escritor, metadados, signer=assinante.assinador).getvalue()


def _alterar(conteudo: bytes) -> bytes:
    """Muda um byte dentro da área coberta pelas assinaturas (no comentário do cabeçalho)."""
    posicao = conteudo.find(b"ReportLab", 0, 400)
    if posicao == -1:
        raise ValueError("marca do cabeçalho não encontrada para simular a alteração")
    return conteudo[:posicao] + b"X" + conteudo[posicao + 1:]


def assinar_pdf(conteudo: bytes, autor: Assinante | None, proprietario: Assinante | None,
                alterar_depois: bool = False) -> bytes:
    if autor:
        conteudo = _assinar(conteudo, autor, "AssinaturaAutor")
    if proprietario:
        conteudo = _assinar(conteudo, proprietario, "AssinaturaProprietario")
    if alterar_depois:
        conteudo = _alterar(conteudo)
    return conteudo
