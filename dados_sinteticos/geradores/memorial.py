"""Memorial descritivo fictício: PDF com texto selecionável e versão impressa e escaneada.

O memorial é um documento do AUTOR: mostra os mesmos valores das pranchas, inclusive os erros e
as omissões injetados (cota omitida na prancha → o valor também não aparece no memorial). A
exceção é o erro "memorial_area_divergente", em que a área total do memorial difere do quadro.

Além dos valores conferidos (áreas, índices, recuos, alturas), traz especificações técnicas com
números que NÃO são procurados (resistência do concreto, pé-direito, caixa d'água, inclinação
do telhado...), para testar se a extração distingue o que importa.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from datetime import date

from PIL import Image, ImageDraw
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import Image as ImagemPlatypus
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from dados_sinteticos.geradores.desenho import formatar_numero  # registra as fontes Vera
from dados_sinteticos.geradores.escaneado import (
    DocumentoEscaneado,
    Estilo,
    Linha,
    Pagina,
    gerar_pdf_escaneado,
    paginar,
    quebrar,
)
from dados_sinteticos.geradores.especificacao import Projeto
from dados_sinteticos.geradores.registro import AVISO_FICTICIO, data_por_extenso

# <b> nos parágrafos precisa saber qual é o negrito da Vera
registerFontFamily("Vera", normal="Vera", bold="VeraBd", italic="Vera", boldItalic="VeraBd")

ESTILO_MEMORIAL_ESCANEADO = Estilo(fonte="arial", formato="A4", cor_papel="branco",
                                   corpo_pt=11.0, entrelinha_pt=15.0, margem_pt=60.0)


def n(valor: float) -> str:
    return formatar_numero(valor)


@dataclass
class Secao:
    titulo: str
    campos: list[tuple[str, str]] = field(default_factory=list)  # "Rótulo: valor"
    paragrafos: list[str] = field(default_factory=list)
    tabela: list[tuple[str, str]] = field(default_factory=list)  # quadro (descrição, valor)


@dataclass
class Memorial:
    secoes: list[Secao]
    municipio: str
    data: date
    autor: str
    registro_autor: str
    proprietario: str  # "" quando a prancha também omite o proprietário
    assinado_autor: bool = True  # espelha as assinaturas das pranchas
    assinado_proprietario: bool = True


def gerar_memorial(projeto: Projeto) -> Memorial:
    p, ident, e, a = projeto, projeto.identificacao, projeto.edificacao, projeto.apresentacao
    rng = random.Random(p.semente * 71)
    omitidas = set(a.cotas_omitidas)
    proprietario = ident.proprietario if a.mostrar_proprietario else ""

    identificacao = [
        ("Obra", f"{ident.titulo.title()} - residência unifamiliar"),
        ("Endereço", f"{ident.endereco}, Lote {ident.lote}, Quadra {ident.quadra}, "
                     f"{ident.condominio}, {ident.municipio}"),
        ("Matrícula", f"nº {p.matricula_prancha} do {ident.cartorio}"),
    ]
    if proprietario:
        identificacao.append(("Proprietário(a)", proprietario))
    identificacao += [
        ("Autor(a) do projeto", f"{ident.autor} - {ident.registro_autor}"),
        ("RRT", ident.rrt),
    ]
    if not p.variacao.revisao_em_branco:  # espelha o carimbo
        identificacao.append(("Revisão", ident.revisao))

    terreno = [f"O terreno possui área de {n(p.area_terreno_prancha)} m², conforme matrícula"]
    if "testada" not in omitidas:
        terreno[0] += f", com testada de {n(p.terreno.testada)} m para a via interna"
    terreno[0] += f" e profundidade de {n(p.terreno.profundidade)} m."
    terreno.append("O terreno é plano, sem necessidade de cortes ou aterros significativos.")

    pavimentos = ["Pavimento térreo", "Pavimento superior"]
    quadro = [(f"Área construída - {nome.lower()}", f"{n(area)} m²")
              for nome, area in zip(pavimentos, e.areas_pavimentos, strict=False)]
    quadro += [
        ("Área construída total", f"{n(p.area_total_memorial)} m²"),
        ("Área de projeção da edificação", f"{n(e.projecao)} m²"),
        ("Área permeável", f"{n(e.area_permeavel)} m²"),
        ("Taxa de ocupação", f"{n(p.to_prancha)} %"),
        ("Coeficiente de aproveitamento", n(p.ca_prancha)),
        ("Taxa de permeabilidade", f"{n(p.tp_prancha)} %"),
        ("Número de pavimentos", str(len(e.areas_pavimentos))),
    ]

    recuos = []
    for elemento, rotulo, valor in (
        ("recuo_frontal", "frontal", e.recuo_frontal),
        ("recuo_lateral_e", "lateral esquerdo", e.recuo_lateral_e),
        ("recuo_lateral_d", "lateral direito", p.recuo_lateral_d),
        ("recuo_fundos", "de fundos", p.recuo_fundos),
    ):
        if elemento not in omitidas:
            recuos.append((f"Recuo {rotulo}", f"{n(valor)} m"))
    alturas = []
    if "altura_total" not in omitidas:
        alturas.append(f"A altura total da edificação, medida do nível do passeio ao ponto mais "
                       f"alto da cobertura, é de {n(e.altura)} m.")
    if "muro" not in omitidas:
        alturas.append(f"O muro de divisa terá altura de {n(e.muro_altura)} m, em alvenaria "
                       f"rebocada e pintada.")

    fck = rng.choice([20, 25, 30])
    litros = rng.choice(["1.000", "1.500", "2.000"])
    especificacoes = [
        f"FUNDAÇÕES: sapatas isoladas e vigas baldrame em concreto armado com fck de {fck} MPa, "
        f"dimensionadas conforme sondagem do terreno.",
        f"ESTRUTURA: pilares, vigas e lajes em concreto armado (fck {fck} MPa); pé-direito de "
        f"{n(rng.choice([2.8, 2.9, 3.0]))} m no térreo e {n(rng.choice([2.7, 2.8]))} m no "
        f"pavimento superior.",
        "VEDAÇÕES: alvenaria de blocos cerâmicos de 14 cm, com reboco e pintura acrílica.",
        f"COBERTURA: telha cerâmica sobre estrutura de madeira, com inclinação de "
        f"{rng.choice([30, 35, 40])}% e beiral de {n(rng.choice([0.6, 0.8]))} m.",
        "ESQUADRIAS: portas internas de madeira de 0,80 x 2,10 m; janelas em alumínio com vidro "
        "temperado de 6 mm.",
        f"INSTALAÇÕES: reservatório de água de {litros} litros; esgoto ligado à rede do "
        f"condomínio; águas pluviais conduzidas à sarjeta.",
    ]
    if rng.random() < 0.5:
        especificacoes.append(f"PISCINA: em concreto armado, com área de "
                              f"{n(rng.choice([18.0, 24.0, 32.0]))} m² e profundidade de 1,40 m.")

    secoes = [
        Secao("1. IDENTIFICAÇÃO", campos=identificacao),
        Secao("2. DO TERRENO", paragrafos=terreno),
        Secao("3. DA EDIFICAÇÃO",
              paragrafos=[f"Residência unifamiliar de {len(e.areas_pavimentos)} pavimentos, "
                          f"com sala, cozinha, área de serviço, lavabo e garagem no térreo, e "
                          f"suítes no pavimento superior."],
              tabela=quadro),
        Secao("4. AFASTAMENTOS", campos=recuos),
        Secao("5. ALTURAS", paragrafos=alturas),
        Secao("6. ESPECIFICAÇÕES TÉCNICAS", paragrafos=especificacoes),
        Secao("7. RESPONSABILIDADE TÉCNICA", paragrafos=[
            "O presente memorial é parte integrante do projeto arquitetônico e deve ser lido em "
            "conjunto com as pranchas. A execução da obra observará as normas técnicas vigentes."]),
    ]
    secoes = [s for s in secoes if s.campos or s.paragrafos or s.tabela]
    return Memorial(secoes, ident.municipio, date(2026, rng.randint(1, 9), rng.randint(1, 28)),
                    ident.autor, ident.registro_autor, proprietario,
                    a.assinatura_autor, a.assinatura_proprietario)


# ---------------------------------------------------------------- PDF com texto


_NORMAL = ParagraphStyle("normal", fontName="Vera", fontSize=10, leading=14,
                         alignment=TA_JUSTIFY, spaceAfter=4)
_TITULO = ParagraphStyle("titulo", fontName="VeraBd", fontSize=14, leading=18,
                         alignment=TA_CENTER, spaceAfter=4)
_SECAO = ParagraphStyle("secao", fontName="VeraBd", fontSize=11, leading=15, spaceBefore=8,
                        spaceAfter=4)
_CENTRO = ParagraphStyle("centro", parent=_NORMAL, alignment=TA_CENTER)


def gerar_memorial_pdf(memorial: Memorial) -> bytes:
    """Memorial digitado (texto selecionável), como sai de um editor de texto."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=25 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title="MEMORIAL DESCRITIVO - DOCUMENTO FICTÍCIO",
                            author=memorial.autor, invariant=True)  # bytes reprodutíveis
    elementos = [Paragraph("MEMORIAL DESCRITIVO", _TITULO),
                 Paragraph(AVISO_FICTICIO, _CENTRO), Spacer(1, 6 * mm)]
    for secao in memorial.secoes:
        elementos.append(Paragraph(secao.titulo, _SECAO))
        for rotulo, valor in secao.campos:
            elementos.append(Paragraph(f"<b>{rotulo}:</b> {valor}", _NORMAL))
        for paragrafo in secao.paragrafos:
            elementos.append(Paragraph(paragrafo, _NORMAL))
        if secao.tabela:
            tabela = Table([["Descrição", "Valor"], *secao.tabela], colWidths=[110 * mm, 40 * mm])
            tabela.setStyle(TableStyle([
                ("FONT", (0, 0), (-1, -1), "Vera", 9.5),
                ("FONT", (0, 0), (-1, 0), "VeraBd", 9.5),
                ("GRID", (0, 0), (-1, -1), 0.4, (0, 0, 0)),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]))
            elementos += [Spacer(1, 2 * mm), tabela, Spacer(1, 2 * mm)]
    elementos += [Spacer(1, 8 * mm),
                  Paragraph(f"{memorial.municipio}, {data_por_extenso(memorial.data)}.", _CENTRO),
                  Spacer(1, 14 * mm)]
    for nome, papel, _ in _assinantes(memorial):
        elementos += [Paragraph("_" * 40, _CENTRO), Paragraph(f"{nome}<br/>{papel}", _CENTRO),
                      Spacer(1, 10 * mm)]
    doc.build(elementos)
    return buffer.getvalue()


def _assinantes(memorial: Memorial) -> list[tuple[str, str, bool]]:
    """(nome, papel, assinou) de cada campo de assinatura do fecho."""
    assinantes = [(memorial.autor, f"Autor(a) do projeto - {memorial.registro_autor}",
                   memorial.assinado_autor)]
    if memorial.proprietario:
        assinantes.append((memorial.proprietario, "Proprietário(a)",
                           memorial.assinado_proprietario))
    return assinantes


# ---------------------------------------------------------------- memorial narrativo


def _quadro_como_imagem(linhas: list[tuple[str, str]]) -> bytes:
    """Quadro de áreas desenhado como imagem (como um quadro colado do CAD no Word)."""
    from dados_sinteticos.geradores.escaneado import _fonte

    escala = 150 / 72  # 150 dpi
    altura_linha, largura = round(16 * escala), round(330 * escala)
    imagem = Image.new("RGB", (largura, altura_linha * (len(linhas) + 1) + 2), "white")
    d = ImageDraw.Draw(imagem)
    fonte, negrito = _fonte("arial", False, round(9 * escala)), _fonte("arial", True,
                                                                        round(9 * escala))
    divisa = round(largura * 0.68)
    for i, (rotulo, valor) in enumerate([("QUADRO DE ÁREAS", ""), *linhas]):
        y = i * altura_linha
        d.rectangle([0, y, largura - 1, y + altura_linha], outline="black", width=2)
        d.line([divisa, y, divisa, y + altura_linha], fill="black", width=2)
        d.text((8, y + altura_linha / 2), rotulo, font=negrito if i == 0 else fonte, fill="black",
               anchor="lm")
        d.text((largura - 8, y + altura_linha / 2), valor, font=fonte, fill="black", anchor="rm")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class MemorialNarrativo:
    pdf: bytes
    texto_da_imagem: list[str]  # verdade do OCR do quadro de áreas (que é imagem)


def gerar_memorial_narrativo(projeto: Projeto) -> MemorialNarrativo:
    """Memorial curto, em texto corrido, como o exemplo real (docs/06 §6.2).

    Lista os ambientes com a área útil (as mesmas das plantas, mais deck e piscina) e resume
    os números numa frase; o quadro de áreas é uma IMAGEM (só o OCR consegue lê-lo).
    """
    from dados_sinteticos.geradores.pranchas import AMBIENTES_SUPERIOR, AMBIENTES_TERREO, area_util

    p, ident, e, a = projeto, projeto.identificacao, projeto.edificacao, projeto.apresentacao
    rng = random.Random(p.semente * 71)

    def ambientes(lista) -> list[str]:
        return [f"{nome.lower() if i else nome} ({n(area_util(e, amb))}m²)"
                for i, (nome, amb) in enumerate((amb[0], amb) for amb in lista
                                                if amb[5] is not None)]

    terreo = ambientes(AMBIENTES_TERREO)
    if rng.random() < 0.6:
        terreo += [f"deck ({n(rng.choice([18.5, 24.0, 32.4]))}m²)",
                   f"piscina ({n(rng.choice([18.0, 24.0, 28.3]))}m²)"]
    superior = ambientes(AMBIENTES_SUPERIOR)
    resumo = (f"A edificação em questão possui área construída total de "
              f"{n(p.area_total_memorial)}m², a área permeável é de {n(e.area_permeavel)}m², "
              f"resultando uma taxa de permeabilidade de {n(p.tp_prancha)}%; a taxa de ocupação "
              f"é {n(p.to_prancha)}%, coeficiente de aproveitamento {n(p.ca_prancha)}")
    if "altura_total" not in a.cotas_omitidas:
        resumo += f", totalizando {n(e.altura)}m de altura"
    quadro = [("Área do terreno", f"{n(p.area_terreno_prancha)} m²"),
              ("Área construída térreo", f"{n(e.areas_pavimentos[0])} m²"),
              ("Área construída superior", f"{n(e.areas_pavimentos[1])} m²"),
              ("Área construída total", f"{n(p.area_total_memorial)} m²"),
              ("Área de projeção", f"{n(e.projecao)} m²"),
              ("Área permeável", f"{n(e.area_permeavel)} m²"),
              ("Taxa de ocupação", f"{n(p.to_prancha)} %"),
              ("Coeficiente de aproveitamento", n(p.ca_prancha)),
              ("Taxa de permeabilidade", f"{n(p.tp_prancha)} %")]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title="MEMORIAL DESCRITIVO - DOCUMENTO FICTÍCIO",
                            author=ident.autor, invariant=True)
    normal = ParagraphStyle("n", parent=_NORMAL, fontSize=11, leading=15)
    elementos = [Paragraph("MEMORIAL DESCRITIVO", _TITULO), Paragraph("_" * 54, _CENTRO),
                 Paragraph(AVISO_FICTICIO, _CENTRO), Spacer(1, 6 * mm)]
    if a.mostrar_proprietario:
        elementos.append(Paragraph(f"<b>Proprietário:</b> {ident.proprietario}", normal))
    elementos += [
        Paragraph(f"<b>Endereço:</b> {ident.endereco}, Lote {ident.lote}, Quadra "
                  f"{ident.quadra}, {ident.condominio}, {ident.municipio}.", normal),
        Spacer(1, 4 * mm),
        Paragraph("Trata-se de uma edificação unifamiliar de dois pavimentos, contendo os "
                  "seguintes ambientes:", normal),
        Paragraph(f"Térreo: {', '.join(terreo[:-1])} e {terreo[-1]}.", normal),
        Paragraph(f"Superior: {', '.join(superior[:-1])} e {superior[-1]}.", normal),
        Paragraph(resumo + ".", normal),
        Paragraph("Quadro de áreas:", normal),
        Spacer(1, 2 * mm),
        ImagemPlatypus(io.BytesIO(_quadro_como_imagem(quadro)), width=120 * mm,
                       height=120 * mm * (len(quadro) + 1) * 16 / 330),
        Spacer(1, 18 * mm),
        Paragraph("_" * 45, _CENTRO),
        Paragraph(f"{ident.autor.upper()}<br/>Arquiteto(a) e Urbanista - {ident.registro_autor}",
                  _CENTRO),
    ]
    doc.build(elementos)
    linhas_imagem = ["QUADRO DE ÁREAS", *[f"{rotulo} {valor}" for rotulo, valor in quadro]]
    return MemorialNarrativo(buffer.getvalue(), linhas_imagem)


# ---------------------------------------------------------------- versão escaneada


def paginas_do_memorial(memorial: Memorial) -> list[Pagina]:
    """O mesmo memorial, impresso, assinado à caneta e escaneado."""
    estilo = ESTILO_MEMORIAL_ESCANEADO
    blocos: list[list[Linha]] = []
    for secao in memorial.secoes:
        linhas = [Linha(secao.titulo, negrito=True)]
        for rotulo, valor in secao.campos:
            linhas += quebrar(f"{rotulo}: {valor}", estilo, recuo=0,
                              prefixo_negrito=len(rotulo) + 1)
        for paragrafo in secao.paragrafos:
            linhas += quebrar(paragrafo, estilo)
        for descricao, valor in secao.tabela:  # quadro como linhas com pontilhado
            pontos = "." * max(3, 70 - len(descricao) - len(valor))
            linhas.append(Linha(f"{descricao} {pontos} {valor}"))
        blocos.append(linhas)
    fecho = [Linha(f"{memorial.municipio}, {data_por_extenso(memorial.data)}.", "centro"),
             Linha(""), Linha(""), Linha("")]
    for nome, papel, assinou in _assinantes(memorial):
        fecho += [Linha("_" * 40, "centro", assinar=assinou), Linha(nome, "centro"),
                  Linha(papel, "centro"), Linha(""), Linha("")]
    blocos.append(fecho)

    def cabecalho(numero_pagina: int) -> list[Linha]:
        topo = [Linha(AVISO_FICTICIO, "centro")]
        if numero_pagina == 1:
            topo.insert(0, Linha("MEMORIAL DESCRITIVO", "centro", negrito=True, escala=1.4))
        return topo

    return paginar(blocos, cabecalho, estilo, reserva_final=4, moldura_no_cabecalho=False)


def gerar_memorial_escaneado(memorial: Memorial, qualidade: str,
                             semente: int) -> DocumentoEscaneado:
    return gerar_pdf_escaneado(paginas_do_memorial(memorial), qualidade, semente,
                               ESTILO_MEMORIAL_ESCANEADO)
