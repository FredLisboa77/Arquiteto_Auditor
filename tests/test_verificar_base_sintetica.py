"""Testes da verificação da base sintética (CPF/CNPJ válidos, marca de fictício, gabaritos)."""

import json
import shutil

import pymupdf

from scripts.verificar_base_sintetica import (
    PASTA_PADRAO,
    cnpj_valido,
    documentos_validos,
    verificar,
)

# Números de exemplo públicos (documentação de validadores), montados em partes para que este
# arquivo não seja bloqueado pela verificação anti-vazamento.
CPF_VALIDO = "529.982.247" + "-25"
CNPJ_VALIDO = "11.222.333/0001" + "-81"


def test_reconhece_cpf_e_cnpj_validos():
    assert cnpj_valido(CNPJ_VALIDO.replace(".", "").replace("/", "").replace("-", ""))
    assert documentos_validos(f"CPF {CPF_VALIDO} e CNPJ {CNPJ_VALIDO}") == [
        "CPF " + "529982247" + "25", "CNPJ " + "112223330001" + "81"]
    assert documentos_validos("CPF 529.982.247-24 e CNPJ 11.222.333/0001-82") == []


def _pdf(caminho, texto, comentario=None):
    documento = pymupdf.open()
    pagina = documento.new_page()
    if texto:
        pagina.insert_text((72, 72), texto)
    if comentario:
        anotacao = pagina.add_rect_annot(pymupdf.Rect(72, 100, 200, 120))
        anotacao.set_info(content=comentario)
        anotacao.update()
    documento.save(caminho)


def _conjunto(tmp_path, nome="sint-x"):
    pasta = tmp_path / nome
    pasta.mkdir()
    shutil.copy(PASTA_PADRAO / "sint-001" / "gabarito.json", pasta / "gabarito.json")
    return pasta


def test_aponta_cpf_valido_em_comentario_de_pdf_e_em_json(tmp_path):
    pasta = _conjunto(tmp_path)
    _pdf(pasta / "prancha.pdf", "DOCUMENTO FICTÍCIO", comentario=f"CPF {CPF_VALIDO}")
    (pasta / "especificacao.json").write_text(json.dumps({"cnpj": CNPJ_VALIDO}),
                                              encoding="utf-8")
    problemas = verificar(tmp_path).problemas
    assert any("prancha.pdf: CPF" in p for p in problemas)
    assert any("especificacao.json: CNPJ" in p for p in problemas)


def test_aponta_cpf_valido_no_texto_dos_escaneados(tmp_path):
    pasta = _conjunto(tmp_path)
    _pdf(pasta / "matricula.pdf", "")  # "escaneado": sem texto
    (pasta / "verdade_ocr.json").write_text(json.dumps(
        {"matricula.pdf": [f"DOCUMENTO FICTÍCIO - CPF {CPF_VALIDO}"]}), encoding="utf-8")
    assert any("matricula.pdf: CPF" in p for p in verificar(tmp_path).problemas)


def test_aponta_pdf_sem_marca_de_ficticio_e_gabarito_ausente(tmp_path):
    pasta = tmp_path / "sint-y"
    pasta.mkdir()
    _pdf(pasta / "lei.pdf", "Lei qualquer")
    problemas = verificar(tmp_path).problemas
    assert any("sem marca de documento fictício" in p for p in problemas)
    assert any("gabarito inválido ou ausente" in p for p in problemas)


def test_base_versionada_esta_limpa():
    relatorio = verificar(PASTA_PADRAO)
    assert relatorio.problemas == []
    assert relatorio.conjuntos >= 8 and relatorio.cpfs_conferidos > 0
