"""Assinaturas digitais de um PDF, lidas e conferidas localmente com o pyHanko (docs/03 §3).

Para cada assinatura: campo, titular e emissor do certificado, data informada, e:
- integra: o conteúdo coberto pela assinatura não mudou depois de assinado (resumo e
  criptografia conferem);
- cobre_arquivo_inteiro: nada foi salvo no arquivo depois desta assinatura. Basta que UMA
  assinatura cubra o arquivo inteiro (normalmente a última); se nenhuma cobre, houve
  alteração salva depois de todas as assinaturas;
- confiavel: o certificado tem cadeia até uma raiz confiável. Nada é consultado na internet
  (LGPD): sem as raízes da ICP-Brasil guardadas localmente, fica False — a validação oficial
  (validar.iti.gov.br) é orientação no relatório, feita pelo usuário.
LGPD: o titular do e-CPF vem como "NOME:CPF"; o CPF é removido antes de guardar.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.validation.errors import SignatureValidationError
from pyhanko.sign.validation.status import SignatureCoverageLevel
from pyhanko_certvalidator import ValidationContext

from arquiteto_auditor.dominio.documento import AssinaturaDigital

# Sem raízes confiáveis, o pyHanko registra cada certificado como erro no log; é esperado.
logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)

# Raízes confiáveis: nenhuma por enquanto (as da ICP-Brasil, guardadas localmente, entram
# depois). Explícito para não depender da lista de certificados do Windows.
RAIZES_CONFIAVEIS: list = []

_CPF = re.compile(r"\s*:?\s*\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s*")


def nome_do_titular(nome_comum: str | None) -> str | None:
    """Nome do titular sem o CPF ("FULANO DE TAL:12345678900" → "FULANO DE TAL")."""
    if not nome_comum:
        return None
    return _CPF.sub(" ", nome_comum).strip(" :") or None


def ler_assinaturas(caminho: Path) -> list[AssinaturaDigital]:
    assinaturas = []
    with open(caminho, "rb") as arquivo:
        try:
            leitor = PdfFileReader(arquivo, strict=False)
            embutidas = leitor.embedded_signatures
        except Exception as erro:  # PDF malformado: sem assinaturas legíveis
            logging.getLogger(__name__).warning("assinaturas ilegíveis: %s", type(erro).__name__)
            return []
        for assinatura in embutidas:
            certificado = assinatura.signer_cert
            dados = {
                "campo": assinatura.field_name,
                "titular": nome_do_titular(certificado.subject.native.get("common_name")),
                "emissor": certificado.issuer.native.get("common_name"),
            }
            try:
                situacao = validate_pdf_signature(assinatura, ValidationContext(
                    trust_roots=RAIZES_CONFIAVEIS, allow_fetching=False))
            except (SignatureValidationError, ValueError) as erro:
                assinaturas.append(AssinaturaDigital(
                    **dados, integra=False, cobre_arquivo_inteiro=False, confiavel=False,
                    erro=type(erro).__name__))
                continue
            assinaturas.append(AssinaturaDigital(
                **dados, data=situacao.signer_reported_dt,
                integra=bool(situacao.intact and situacao.valid),
                cobre_arquivo_inteiro=situacao.coverage == SignatureCoverageLevel.ENTIRE_FILE,
                confiavel=bool(situacao.trusted)))
    return assinaturas
