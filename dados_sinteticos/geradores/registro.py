"""Conteúdo de documentos registrais fictícios: matrícula (e, depois, escritura).

A matrícula mostra a VERDADE registral do projeto sintético (área real do terreno, proprietário
atual). Para testar a leitura do "estado atual" do imóvel (Fase 7), ela pode trazer de propósito
valores antigos que foram mudados por atos posteriores:
- a abertura descreve uma área ANTIGA, corrigida depois por uma averbação de retificação;
- o primeiro comprador pode não ser o proprietário atual (houve uma segunda venda);
- uma hipoteca/alienação fiduciária pode aparecer registrada e depois cancelada.

Todos os nomes vêm do Faker; CPFs e CNPJs têm dígitos verificadores ERRADOS de propósito.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker

from dados_sinteticos.geradores.desenho import formatar_numero
from dados_sinteticos.geradores.escaneado import (
    Carimbo,
    DocumentoEscaneado,
    Estilo,
    Linha,
    Pagina,
    gerar_pdf_escaneado,
    paginar,
    quebrar,
)
from dados_sinteticos.geradores.especificacao import Projeto, cpf_invalido

_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro")
_PROFISSOES = ("engenheiro(a)", "médico(a)", "professor(a)", "empresário(a)", "advogado(a)",
               "servidor(a) público(a)", "administrador(a)", "contador(a)")


# ---------------------------------------------------------------- números e datas por extenso


_UNIDADES = ("", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
             "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito",
             "dezenove")
_DEZENAS = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
            "oitenta", "noventa")
_CENTENAS = ("", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
             "setecentos", "oitocentos", "novecentos")


def _ate_999(n: int) -> str:
    if n == 100:
        return "cem"
    partes = []
    if n >= 100:
        partes.append(_CENTENAS[n // 100])
        n %= 100
    if n >= 20:
        partes.append(_DEZENAS[n // 10])
        n %= 10
    if n:
        partes.append(_UNIDADES[n])
    return " e ".join(partes)


def por_extenso(n: int) -> str:
    """Inteiro de 0 a 999.999 por extenso ("quatrocentos e cinquenta")."""
    if not 0 <= n < 1_000_000:
        raise ValueError("por_extenso aceita de 0 a 999.999")
    if n == 0:
        return "zero"
    milhares, resto = divmod(n, 1000)
    if not milhares:
        return _ate_999(resto)
    texto = "mil" if milhares == 1 else f"{_ate_999(milhares)} mil"
    if not resto:
        return texto
    # "mil e cem", "mil e vinte", mas "mil cento e vinte"
    ligacao = " e " if resto < 100 or resto % 100 == 0 else " "
    return texto + ligacao + _ate_999(resto)


def area_por_extenso(area: float) -> str:
    """450.5 → "quatrocentos e cinquenta metros quadrados e cinquenta decímetros quadrados"."""
    inteiro = int(area)
    centesimos = round((area - inteiro) * 100)
    texto = f"{por_extenso(inteiro)} metros quadrados"
    if centesimos:
        texto += f" e {por_extenso(centesimos)} decímetros quadrados"
    return texto


def data_por_extenso(d: date) -> str:
    return f"{d.day:02d} de {_MESES[d.month - 1]} de {d.year}"


def br(valor: float) -> str:
    return formatar_numero(valor)


def cnpj_invalido(rng: random.Random) -> str:
    """CNPJ com formato correto e dígitos verificadores ERRADOS (nunca coincide com um real)."""
    base = [rng.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    for pesos in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
        resto = sum(d * p for d, p in zip(base, pesos, strict=False)) % 11
        base.append(0 if resto < 2 else 11 - resto)
    base[13] = (base[13] + 1 + rng.randint(0, 8)) % 10  # estraga o último dígito
    d = "".join(map(str, base))
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


# ---------------------------------------------------------------- estrutura


@dataclass
class Ato:
    codigo: str  # "R-1", "AV-2"...
    data: date
    titulo: str
    texto: str


@dataclass
class Parte:
    nome: str
    documento: str  # CPF (pessoa) ou CNPJ (empresa), sempre com dígitos inválidos
    profissao: str | None = None  # None = pessoa jurídica

    def qualificacao(self, municipio: str) -> str:
        if self.profissao is None:
            return (f"{self.nome}, inscrita no CNPJ sob nº {self.documento}, com sede em "
                    f"{municipio}")
        return (f"{self.nome}, brasileiro(a), {self.profissao}, portador(a) do CPF nº "
                f"{self.documento}, residente e domiciliado(a) em {municipio}")


@dataclass
class Venda:
    """Dados de uma compra e venda, para a escritura ficar coerente com o registro."""

    codigo_ato: str  # "R-1"
    vendedor: Parte
    comprador: Parte
    valor: int
    data_escritura: date
    livro: int
    folhas: int
    # descrição do imóvel VIGENTE na data da escritura (pode ser anterior a uma retificação)
    testada: float
    profundidade: float
    area: float


@dataclass
class Matricula:
    numero: str
    cartorio: str
    municipio: str
    estado: str
    data_abertura: date
    abertura: str  # descrição do imóvel na abertura
    atos: list[Ato] = field(default_factory=list)
    vendas: list[Venda] = field(default_factory=list)
    data_certidao: date | None = None
    # Verdade do estado ATUAL (depois de todos os atos), para o gabarito e os testes.
    area_atual: float = 0.0
    proprietario_atual: str = ""
    onus_ativos: list[str] = field(default_factory=list)

    def paragrafos(self) -> list[str]:
        """Texto corrido do documento, na ordem em que aparece (cabeçalho é desenhado à parte)."""
        textos = [self.abertura]
        for ato in self.atos:
            textos.append(f"{ato.codigo}/{self.numero} - Em {data_por_extenso(ato.data)}. "
                          f"{ato.titulo}: {ato.texto}")
        return textos


# ---------------------------------------------------------------- geração


def _descricao_lote(projeto: Projeto, testada: float, profundidade: float, area: float) -> str:
    ident = projeto.identificacao
    lote = int(ident.lote)
    vizinho_esquerdo = lote - 1 if lote > 1 else lote + 2
    return (
        f"Lote de terreno sob nº {ident.lote} da Quadra {ident.quadra} do {ident.condominio}, "
        f"situado na {ident.endereco}, no município de {ident.municipio}, com a área de "
        f"{br(area)} m² ({area_por_extenso(area)}), medindo {br(testada)} m de frente para a "
        f"via de circulação interna; {br(profundidade)} m da frente aos fundos, de ambos os "
        f"lados; e {br(testada)} m nos fundos; confrontando pelo lado direito com o lote "
        f"nº {lote + 1}, pelo lado esquerdo com o lote nº {vizinho_esquerdo} e nos fundos "
        f"com área verde do condomínio."
    )


def gerar_matricula(projeto: Projeto, variante: int = 0) -> Matricula:
    """Monta a matrícula fictícia do terreno do projeto.

    `variante` muda o sorteio dos atos sem mudar a verdade (área e proprietário atuais).
    """
    rng = random.Random(projeto.semente * 31 + variante)
    fake = Faker("pt_BR")
    fake.seed_instance(projeto.semente * 31 + variante)
    ident, terreno = projeto.identificacao, projeto.terreno

    def pessoa() -> str:
        return f"{fake.first_name()} {fake.last_name()} {fake.last_name()}"

    def pessoa_fisica(nome: str) -> Parte:
        return Parte(nome, cpf_invalido(rng), rng.choice(_PROFISSOES))

    loteadora = Parte(f"{fake.last_name()} Empreendimentos Imobiliários Ltda.",
                      cnpj_invalido(rng))
    abertura_data = date(rng.randint(2010, 2016), rng.randint(1, 12), rng.randint(1, 28))

    # Área na abertura: às vezes diferente da real (corrigida depois por retificação).
    retificar = rng.random() < 0.6
    if retificar:
        profundidade_antiga = round(terreno.profundidade + rng.choice([-0.4, -0.25, 0.3, 0.5]), 2)
    else:
        profundidade_antiga = terreno.profundidade
    area_antiga = round(terreno.testada * profundidade_antiga, 2)

    abertura = (
        f"IMÓVEL: {_descricao_lote(projeto, terreno.testada, profundidade_antiga, area_antiga)} "
        f"PROPRIETÁRIA: {loteadora.qualificacao(ident.municipio)}. REGISTRO ANTERIOR: "
        f"Matrícula nº {rng.randint(100, 999)} deste "
        f"Registro, R-{rng.randint(2, 9)} (loteamento). O Oficial."
    )
    matricula = Matricula(numero=ident.matricula, cartorio=ident.cartorio,
                          municipio=ident.municipio, estado=fake.estado_nome(),
                          data_abertura=abertura_data,
                          abertura=abertura)

    data = abertura_data
    numero_ato = 0
    profundidade_vigente, area_vigente = profundidade_antiga, area_antiga

    def proximo(codigo: str, titulo: str, texto: str) -> None:
        nonlocal data, numero_ato
        numero_ato += 1
        data = data + timedelta(days=rng.randint(60, 700))
        matricula.atos.append(Ato(f"{codigo}-{numero_ato}", data, titulo, texto))

    def venda(vendedor: Parte, comprador: Parte) -> None:
        valor = rng.randint(18, 90) * 10_000
        data_escritura = data + timedelta(days=rng.randint(20, 50))  # o registro vem depois
        livro, folhas = rng.randint(100, 900), rng.randint(1, 300)
        proximo("R", "COMPRA E VENDA", (
            f"Nos termos da escritura pública lavrada em {data_por_extenso(data_escritura)}, "
            f"no Tabelionato de Notas de {ident.municipio}, livro {livro}, folhas {folhas}, "
            f"{vendedor.nome} transmitiu o imóvel desta matrícula, por venda, a "
            f"{comprador.qualificacao(ident.municipio)}. VALOR: R$ {br(valor)}. O Oficial."))
        matricula.vendas.append(Venda(
            f"R-{numero_ato}", vendedor, comprador, valor, data_escritura, livro, folhas,
            terreno.testada, profundidade_vigente, area_vigente))

    segunda_venda = rng.random() < 0.5
    proprietario = pessoa_fisica(ident.proprietario)
    primeiro_comprador = pessoa_fisica(pessoa()) if segunda_venda else proprietario
    venda(loteadora, primeiro_comprador)

    if retificar:
        descricao_correta = _descricao_lote(projeto, terreno.testada, terreno.profundidade,
                                            terreno.area)
        proximo("AV", "RETIFICAÇÃO DE ÁREA", (
            f"A requerimento do(a) proprietário(a), instruído com levantamento topográfico e "
            f"anuência dos confrontantes, procede-se à retificação da descrição do imóvel, que "
            f"passa a ser a seguinte: {descricao_correta} O Oficial."))
        profundidade_vigente, area_vigente = terreno.profundidade, terreno.area

    if rng.random() < 0.5:
        credor = f"Banco {fake.last_name()} S.A."
        proximo("R", "ALIENAÇÃO FIDUCIÁRIA", (
            f"Por instrumento particular, o(a) proprietário(a) alienou fiduciariamente o imóvel "
            f"desta matrícula a {credor}, CNPJ nº {cnpj_invalido(rng)}, em garantia de dívida "
            f"no valor de R$ {br(rng.randint(10, 50) * 10_000)}. O Oficial."))
        codigo_onus = f"R-{numero_ato}"
        if rng.random() < 0.7:
            proximo("AV", "CANCELAMENTO", (
                f"Fica cancelado o registro {codigo_onus}/{ident.matricula}, em virtude de "
                f"autorização dada pelo credor {credor}. O Oficial."))
        else:
            matricula.onus_ativos.append(f"{codigo_onus}/{ident.matricula}")

    if rng.random() < 0.4:
        proximo("AV", "ALTERAÇÃO DE DENOMINAÇÃO", (
            f"Conforme certidão da Prefeitura Municipal de {ident.municipio}, a via de acesso "
            f"ao condomínio passou a denominar-se {ident.endereco.rsplit(',', 1)[0]}. "
            f"O Oficial."))

    if segunda_venda:
        venda(primeiro_comprador, proprietario)

    matricula.data_certidao = date(2026, rng.randint(1, 9), rng.randint(1, 28))
    matricula.area_atual = terreno.area
    matricula.proprietario_atual = ident.proprietario
    return matricula


# ---------------------------------------------------------------- matrícula escaneada


AVISO_FICTICIO = "DOCUMENTO FICTÍCIO - SEM VALOR LEGAL"


ESTILOS_MATRICULA = {
    # ficha antiga datilografada, fotocopiada em papel comum
    "ficha": Estilo(fonte="courier", formato="A4", cor_papel="envelhecido"),
    # certidão de inteiro teor moderna: laser, papel de segurança com faixas nas bordas
    "certidao": Estilo(fonte="times", formato="carta", cor_papel="azulado", faixas_borda=True,
                       corpo_pt=10.5, entrelinha_pt=12.5, margem_pt=50.0),
}


def _codigo_selo(rng: random.Random) -> str:
    letras = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return ("".join(rng.choice(letras) for _ in range(3)) + f"{rng.randint(0, 99999):05d}"
            + "-" + "".join(rng.choice(letras) for _ in range(3)))


def _texto_certidao(m: Matricula) -> str:
    return (
        f"CERTIDÃO - Certifico e dou fé que a presente é reprodução autêntica da matrícula "
        f"nº {m.numero}, extraída nos termos do art. 19, § 1º, da Lei nº 6.015/1973, e que nela "
        f"se encontram lançados todos os atos relativos ao imóvel até a data de hoje. "
        f"{m.municipio}, {data_por_extenso(m.data_certidao)}. O Oficial."
    )


def _fecho(pagina: Pagina, m: Matricula, rng: random.Random) -> None:
    pagina.assinaturas = 1
    pagina.carimbos = [
        Carimbo(["REGISTRO DE", "IMÓVEIS", m.municipio.upper()[:16], "FICTÍCIO"]),
        Carimbo([f"EMOLUMENTOS R$ {br(rng.randint(40, 90) + rng.randint(0, 99) / 100)}",
                 "PROTOCOLO", f"Nº {rng.randint(10_000, 99_999)}"], redondo=False),
    ]
    pagina.selo = _codigo_selo(rng)


def _paginas_ficha(m: Matricula, rng: random.Random, estilo: Estilo) -> list[Pagina]:
    def cabecalho(numero_pagina: int) -> list[Linha]:
        ficha = f"FICHA {numero_pagina:02d}"
        if numero_pagina > 1:
            return [Linha(AVISO_FICTICIO, "centro"),
                    Linha(f"MATRÍCULA Nº {m.numero}".ljust(40) + ficha, negrito=True)]
        return [
            Linha(AVISO_FICTICIO, "centro"),
            Linha(m.cartorio.upper(), "centro", negrito=True),
            Linha("LIVRO Nº 2 - REGISTRO GERAL", "centro"),
            Linha(f"MATRÍCULA Nº {m.numero}".ljust(26) + ficha.ljust(12)
                  + f"{m.municipio}, {m.data_abertura:%d/%m/%Y}", negrito=True),
        ]

    blocos = [quebrar(p, estilo) for p in [*m.paragrafos(), _texto_certidao(m)]]
    paginas = paginar(blocos, cabecalho, estilo, reserva_final=14)
    for pagina in paginas:
        pagina.rubricas_apos = "O Oficial."
    _fecho(paginas[-1], m, rng)
    return paginas


def _paginas_certidao(m: Matricula, rng: random.Random, estilo: Estilo) -> list[Pagina]:
    def cabecalho(numero_pagina: int) -> list[Linha]:
        topo = [Linha("", brasao=True, escala=3.0),
                Linha(m.cartorio.upper(), "centro", negrito=True),
                Linha(f"Comarca de {m.municipio} - Estado de {m.estado}", "centro"),
                Linha(AVISO_FICTICIO, "centro")]
        if numero_pagina > 1:
            return topo
        return [Linha("REPÚBLICA FEDERATIVA DO BRASIL", "centro", negrito=True, escala=1.5),
                Linha(f"ESTADO DE {m.estado.upper()}", "centro", negrito=True, escala=1.5),
                *topo,
                Linha("CERTIDÃO DE INTEIRO TEOR", "centro", negrito=True, escala=1.8),
                Linha(f"MATRÍCULA Nº {m.numero} - LIVRO Nº 2 - REGISTRO GERAL", "centro",
                      negrito=True)]

    def rotulo(paragrafo: str) -> int:  # "IMÓVEL:" ou "R-1/81.735" em negrito
        return len(paragrafo.split(" ")[0])

    blocos = [quebrar(p, estilo, recuo=0, prefixo_negrito=rotulo(p))
              for p in [*m.paragrafos(), _texto_certidao(m)]]
    paginas = paginar(blocos, cabecalho, estilo, reserva_final=16, moldura_no_cabecalho=False)
    _fecho(paginas[-1], m, rng)
    paginas[-1].anular_espaco = True
    # frente e verso: as páginas pares são o verso da folha (sem as faixas da borda)
    if len(paginas) % 2:
        paginas.append(Pagina([], verso=True))
    for numero, pagina in enumerate(paginas, start=1):
        pagina.verso = numero % 2 == 0
        pagina.copias = rng.randint(2, 4) if pagina.linhas else rng.randint(6, 11)
    return paginas


def paginas_da_matricula(m: Matricula, semente: int, estilo: str = "ficha") -> list[Pagina]:
    rng = random.Random(semente)
    if estilo == "ficha":
        return _paginas_ficha(m, rng, ESTILOS_MATRICULA[estilo])
    return _paginas_certidao(m, rng, ESTILOS_MATRICULA[estilo])


def gerar_matricula_escaneada(projeto: Projeto, qualidade: str, variante: int = 0,
                              estilo: str = "certidao") -> tuple[Matricula, DocumentoEscaneado]:
    matricula = gerar_matricula(projeto, variante)
    semente = projeto.semente * 97 + variante
    paginas = paginas_da_matricula(matricula, semente, estilo)
    return matricula, gerar_pdf_escaneado(paginas, qualidade, semente, ESTILOS_MATRICULA[estilo])
