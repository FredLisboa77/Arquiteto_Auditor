from scripts.verificar_vazamento import cpf_valido, problemas_do_caminho, verificar

# CPF de exemplo público (usado em documentação de validadores). Montado em partes
# para que este próprio arquivo de teste não seja bloqueado pela verificação.
CPF_VALIDO = "529982247" + "25"
CPF_VALIDO_FORMATADO = "529.982.247" + "-25"


def test_cpf_valido_reconhece_digitos_verificadores():
    assert cpf_valido(CPF_VALIDO)
    assert not cpf_valido("52998224724")  # último dígito alterado
    assert not cpf_valido("11111111111")  # sequência repetida


def test_bloqueia_qualquer_arquivo_em_dados_privados():
    assert problemas_do_caminho("dados_privados/documentos_reais/matricula.pdf")
    assert problemas_do_caminho("dados_privados/historico/notas.txt")


def test_permite_leiame_de_dados_privados():
    assert problemas_do_caminho("dados_privados/LEIAME.md") == []


def test_bloqueia_pdf_fora_das_pastas_sinteticas():
    assert problemas_do_caminho("matricula.pdf")
    assert problemas_do_caminho("docs/escritura.PDF")
    assert problemas_do_caminho("src/arquiteto_auditor/foto.png")


def test_permite_pdf_sintetico_e_fixtures():
    assert problemas_do_caminho("dados_sinteticos/projetos/sint-001/prancha.pdf") == []
    assert problemas_do_caminho("tests/fixtures/pagina.png") == []


def test_bloqueia_banco_de_dados():
    assert problemas_do_caminho("historico.db")
    assert problemas_do_caminho("qualquer/lugar/dados.sqlite")


def test_aceita_caminho_com_barra_invertida_do_windows():
    assert problemas_do_caminho("dados_privados\\cache\\x.json")


def test_bloqueia_texto_com_cpf_valido(tmp_path):
    conteudo = f'{{"cpf": "{CPF_VALIDO_FORMATADO}"}}'
    (tmp_path / "gabarito.json").write_text(conteudo, encoding="utf-8")
    assert "gabarito.json" in verificar(["gabarito.json"], tmp_path)


def test_aceita_texto_com_cpf_invalido_sintetico(tmp_path):
    (tmp_path / "gabarito.json").write_text('{"cpf": "529.982.247-24"}', encoding="utf-8")
    assert verificar(["gabarito.json"], tmp_path) == {}


def test_bloqueia_arquivo_grande(tmp_path):
    (tmp_path / "dados.csv").write_bytes(b"0" * (6 * 1024 * 1024))
    assert "dados.csv" in verificar(["dados.csv"], tmp_path)
