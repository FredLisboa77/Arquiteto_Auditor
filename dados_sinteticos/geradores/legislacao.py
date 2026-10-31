"""Lei municipal de uso e ocupação do solo e norma de obras do condomínio, fictícias.

A lei traz os parâmetros da PREFEITURA (Projeto.prefeitura) para a zona do lote, no meio de
muitas outras zonas com valores diferentes (distração). A zona do projeto é identificável
porque o perímetro dela (Anexo I) cita o condomínio. Dois modelos de redação:
- "A": parâmetros num anexo em tabela (uma linha por zona);
- "B": parâmetros em artigos por zona, tabela "invertida" (uma coluna por zona) e um artigo
  com redação alterada, em que o texto cita o valor antigo e o novo (armadilha).

A norma do condomínio traz os parâmetros do CONDOMÍNIO (Projeto.condominio): altura do muro
(só o condomínio define) e, às vezes, valores repetidos ou mais exigentes que os da lei
(conflito de propósito: vale a prefeitura, CLAUDE.md princípio 7).

Ambos têm números que NÃO são parâmetros do lote: multas, prazos, edícula, gradil, horário de
obra, exceções que não se aplicam (lote de esquina, testada pequena) e as outras zonas.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from datetime import date

from faker import Faker
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from dados_sinteticos.geradores import memorial as _memorial  # noqa: F401 (família Vera)
from dados_sinteticos.geradores.desenho import formatar_numero
from dados_sinteticos.geradores.escaneado import (
    DocumentoEscaneado,
    Estilo,
    Linha,
    gerar_pdf_escaneado,
    paginar,
    quebrar,
)
from dados_sinteticos.geradores.especificacao import Parametros, Projeto
from dados_sinteticos.geradores.registro import AVISO_FICTICIO, data_por_extenso, por_extenso

ZONAS = (
    ("ZR-1", "Zona Residencial 1", "baixa densidade"),
    ("ZR-2", "Zona Residencial 2", "média densidade"),
    ("ZR-3", "Zona Residencial 3", "média densidade, com uso misto tolerado"),
    ("ZM", "Zona Mista", "usos residencial, comercial e de serviços"),
    ("ZC", "Zona Central", "alta densidade e atividades centrais"),
    ("ZEIS", "Zona Especial de Interesse Social", "habitação de interesse social"),
    ("ZI", "Zona Industrial", "atividades industriais e logísticas"),
    ("ZPA", "Zona de Proteção Ambiental", "preservação e uso sustentável"),
)
ZONAS_RESIDENCIAIS = ("ZR-1", "ZR-2", "ZR-3")

# Os parâmetros que a lei define, na ordem das tabelas: (campo, rótulo, unidade)
CAMPOS_LEI = (
    ("lote_area_min", "Lote mínimo", "m²"),
    ("testada_min", "Testada mínima", "m"),
    ("recuo_frontal_min", "Recuo frontal mínimo", "m"),
    ("recuo_lateral_min", "Recuo lateral mínimo", "m"),
    ("recuo_fundos_min", "Recuo de fundos mínimo", "m"),
    ("to_max", "Taxa de ocupação máxima", "%"),
    ("ca_max", "Coeficiente de aproveitamento máximo", ""),
    ("permeavel_min", "Taxa de permeabilidade mínima", "%"),
    ("altura_max", "Altura máxima da edificação", "m"),
    ("pavimentos_max", "Número máximo de pavimentos", ""),
)


def valor_texto(campo: str, valor: float) -> str:
    if campo == "pavimentos_max":
        return f"{int(valor)} ({por_extenso(int(valor))})"
    if campo in ("to_max", "permeavel_min"):
        return f"{formatar_numero(valor, casas=0 if valor == int(valor) else 2)}%"
    if campo == "ca_max":
        return formatar_numero(valor, casas=1 if round(valor, 1) == valor else 2)
    unidade = dict((c, u) for c, _, u in CAMPOS_LEI)[campo]
    return f"{formatar_numero(valor)} {unidade}"


# ---------------------------------------------------------------- estrutura comum


@dataclass
class Bloco:
    tipo: str  # "titulo", "subtitulo", "ementa", "capitulo", "artigo", "item", "tabela", "quebra"
    texto: str = ""
    linhas: list[list[str]] = field(default_factory=list)  # tabela: 1ª linha = cabeçalho


@dataclass
class DocumentoNormativo:
    titulo: str
    blocos: list[Bloco]


def _romano(numero: int) -> str:
    resultado = ""
    for valor, letras in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while numero >= valor:
            resultado += letras
            numero -= valor
    return resultado


class _Redator:
    """Numera artigos e acumula blocos."""

    def __init__(self):
        self.blocos: list[Bloco] = []
        self.numero = 0
        self.capitulos = 0

    def capitulo(self, nome: str) -> None:
        self.capitulos += 1
        self.bloco("capitulo", f"CAPÍTULO {_romano(self.capitulos)} - {nome}")

    def bloco(self, tipo: str, texto: str = "", linhas=None) -> None:
        self.blocos.append(Bloco(tipo, texto, linhas or []))

    def artigo(self, texto: str, itens: list[str] = ()) -> int:
        self.numero += 1
        rotulo = f"Art. {self.numero}{'º' if self.numero < 10 else '.'}"
        self.bloco("artigo", f"{rotulo} {texto}")
        for item in itens:
            self.bloco("item", item)
        return self.numero


# ---------------------------------------------------------------- lei municipal


@dataclass
class LeiMunicipal:
    documento: DocumentoNormativo
    modelo: str  # "A" ou "B"
    zona: str  # código da zona do lote do projeto
    parametros_por_zona: dict[str, dict[str, float]]
    valor_antigo: tuple[str, float] | None = None  # (campo, valor revogado) no modelo B


def _parametros_das_zonas(projeto: Projeto, zona: str,
                          rng: random.Random) -> dict[str, dict[str, float]]:
    """Valores da zona do projeto = prefeitura; as demais seguem um perfil realista da zona.

    Sempre que o perfil permite, o valor da outra zona é diferente do valor do projeto, para
    que ler a zona errada dê resultado errado.
    """
    proprios = {c: getattr(projeto.prefeitura, c) for c, _, _ in CAMPOS_LEI}
    tabela = {}
    for codigo, _, _ in ZONAS:
        if codigo == zona:
            tabela[codigo] = proprios
            continue
        valores = {}
        for (campo, _, _), opcoes in zip(CAMPOS_LEI, PERFIS_DAS_ZONAS[codigo], strict=True):
            diferentes = [float(v) for v in opcoes if v != proprios[campo]]
            valores[campo] = rng.choice(diferentes or [float(v) for v in opcoes])
        tabela[codigo] = valores
    return tabela


# Perfil de cada zona, na ordem de CAMPOS_LEI: lote, testada, recuos (frontal, lateral, fundos),
# TO, CA, permeabilidade, altura e pavimentos.
PERFIS_DAS_ZONAS = {
    "ZR-1": ([360, 450, 500], [12, 15], [5, 6], [1.5, 2], [3], [40, 45, 50], [1.0],
             [20, 25, 30], [8.5, 9, 10], [2]),
    "ZR-2": ([250, 300, 360], [10, 12], [4, 5], [1.5], [2, 3], [50, 55, 60], [1.2, 1.5],
             [15, 20], [9, 10, 12], [2, 3]),
    "ZR-3": ([200, 250], [8, 10], [3, 4], [1.5], [1.5, 2], [60, 65], [1.5, 2.0], [15],
             [12, 15], [4]),
    "ZM": ([250, 300], [10, 12], [3, 4], [0, 1.5], [2], [60, 70], [2.0, 2.5], [10, 15],
           [15, 18], [5, 6]),
    "ZC": ([300, 360], [12], [0, 3], [0], [0, 2], [70, 80], [3.0, 4.0], [10], [45, 60],
           [15, 20]),
    "ZEIS": ([125, 150], [5, 6], [3], [0], [1.5], [70], [1.5], [10], [9], [3]),
    "ZI": ([1000, 2000], [20, 25], [10], [3], [5], [60], [1.0], [20], [15, 20], [3]),
    "ZPA": ([2000, 5000], [30], [10], [5], [10], [10, 20], [0.2, 0.3], [70, 80], [7.5], [2]),
}


def _definicoes() -> list[str]:
    return [
        "I - ÁREA CONSTRUÍDA: soma das áreas cobertas de todos os pavimentos da edificação, "
        "medidas pelas faces externas das paredes;",
        "II - ÁREA DE PROJEÇÃO: área da projeção horizontal da edificação sobre o lote, "
        "excluídos os beirais de até 0,80 m (oitenta centímetros);",
        "III - TAXA DE OCUPAÇÃO (TO): relação percentual entre a área de projeção da "
        "edificação e a área do lote;",
        "IV - COEFICIENTE DE APROVEITAMENTO (CA): relação entre a área construída computável e "
        "a área do lote;",
        "V - TAXA DE PERMEABILIDADE (TP): relação percentual entre a área permeável, sem "
        "qualquer tipo de pavimentação ou cobertura, e a área do lote;",
        "VI - RECUO OU AFASTAMENTO: menor distância entre a edificação e a divisa do lote, "
        "medida perpendicularmente a esta;",
        "VII - TESTADA: extensão da divisa do lote voltada para a via pública ou de circulação;",
        "VIII - ALTURA DA EDIFICAÇÃO: distância vertical entre o nível médio do passeio e o "
        "ponto mais alto da cobertura, excluídos caixa d'água, platibanda de até 1,20 m e "
        "elementos técnicos;",
        "IX - PAVIMENTO: espaço da edificação compreendido entre dois pisos consecutivos, ou "
        "entre o piso e a cobertura;",
        "X - EDÍCULA: construção complementar à edificação principal, térrea, destinada a usos "
        "acessórios;",
        "XI - CONDOMÍNIO HORIZONTAL: empreendimento com unidades autônomas de uso residencial "
        "unifamiliar e áreas de uso comum;",
        "XII - LOTE DE ESQUINA: lote situado na confluência de duas vias.",
    ]


_ATIVIDADES = ("Residência unifamiliar", "Residência multifamiliar", "Comércio varejista de "
               "pequeno porte", "Comércio atacadista", "Escritório e consultório", "Escola de "
               "educação infantil", "Ensino fundamental e médio", "Ensino superior", "Clínica "
               "médica", "Hospital", "Templo religioso", "Restaurante e lanchonete", "Bar com "
               "música ao vivo", "Hotel e pousada", "Posto de combustível", "Oficina mecânica",
               "Indústria de baixo impacto", "Indústria de médio impacto", "Depósito e "
               "armazém", "Academia de ginástica", "Supermercado", "Agência bancária",
               "Serviço de lavanderia", "Salão de beleza", "Garagem de veículos",
               "Marcenaria", "Padaria", "Farmácia", "Clube recreativo", "Casa de festas",
               "Creche", "Biblioteca", "Museu e centro cultural", "Cinema e teatro",
               "Laboratório de análises", "Clínica veterinária", "Pet shop", "Floricultura",
               "Loja de materiais de construção", "Concessionária de veículos", "Lava-rápido",
               "Gráfica", "Serralheria", "Transportadora", "Central de reciclagem")


def _capitulos_complementares(r: _Redator) -> None:
    """Capítulos comuns em leis de uso do solo (volume realista e números de distração)."""
    r.capitulo("DO PARCELAMENTO DO SOLO")
    r.artigo("O parcelamento do solo urbano poderá ser feito mediante loteamento, "
             "desmembramento ou condomínio de lotes, observadas a Lei Federal nº 6.766/1979 e "
             "esta Lei.")
    r.artigo("Nos loteamentos, a área destinada ao sistema viário, aos equipamentos públicos e "
             "às áreas verdes corresponderá a, no mínimo, 35% (trinta e cinco por cento) da "
             "gleba.")
    r.artigo("As quadras terão comprimento máximo de 200,00 m (duzentos metros).")
    r.artigo("Não será permitido o parcelamento do solo em terrenos alagadiços, com declividade "
             "igual ou superior a 30% (trinta por cento) ou em áreas de preservação "
             "permanente.")
    r.artigo("O remembramento de lotes é permitido em todas as zonas, desde que o lote "
             "resultante atenda aos parâmetros da zona.")
    r.artigo("O desmembramento somente será aprovado se os lotes resultantes atenderem à área "
             "e à testada mínimas da zona.")

    r.capitulo("DO SISTEMA VIÁRIO")
    r.artigo("As vias públicas classificam-se em arteriais, coletoras e locais, conforme o "
             "Anexo IV.")
    r.artigo("As vias locais terão largura mínima de 12,00 m (doze metros), sendo 7,00 m de "
             "pista de rolamento e 2,50 m de passeio em cada lado.")
    r.artigo("As vias de circulação interna dos condomínios horizontais terão largura mínima "
             "de 10,00 m (dez metros).")
    r.artigo("Nas esquinas, o alinhamento será concordado por arco de círculo com raio mínimo "
             "de 6,00 m (seis metros).")

    r.capitulo("DO ESTACIONAMENTO")
    r.artigo("As edificações deverão dispor de vagas de estacionamento em número mínimo "
             "conforme o Anexo V.")
    r.artigo("Cada vaga terá dimensões mínimas de 2,50 m x 5,00 m (dois metros e cinquenta "
             "centímetros por cinco metros).")
    r.artigo("Nas residências unifamiliares, será exigida no mínimo 1 (uma) vaga por unidade, "
             "dispensada a cobertura.")
    r.artigo("Os acessos de veículos terão largura máxima de 6,00 m (seis metros) por lote.")

    r.capitulo("DO ESTUDO DE IMPACTO DE VIZINHANÇA")
    r.artigo("Dependerão de Estudo de Impacto de Vizinhança (EIV) os empreendimentos com área "
             "construída superior a 5.000,00 m² (cinco mil metros quadrados).")
    r.artigo("O EIV analisará, no mínimo, o adensamento populacional, os equipamentos "
             "urbanos, o uso do solo, a valorização imobiliária, o tráfego, a ventilação, a "
             "iluminação e a paisagem.")
    r.artigo("O EIV será objeto de audiência pública, com antecedência mínima de 15 (quinze) "
             "dias de sua divulgação.")

    r.capitulo("DA OUTORGA ONEROSA DO DIREITO DE CONSTRUIR")
    r.artigo("Na Zona Central e na Zona Mista, o coeficiente de aproveitamento poderá ser "
             "acrescido em até 1,0 (um inteiro) mediante contrapartida financeira.")
    r.artigo("A contrapartida será calculada pela fórmula C = A x V x 0,30, em que C é o valor "
             "da contrapartida, A é a área construída acima do coeficiente básico e V é o valor "
             "venal do metro quadrado do terreno.")
    r.artigo("Os recursos da outorga onerosa serão destinados ao Fundo Municipal de "
             "Desenvolvimento Urbano.")

    r.capitulo("DOS INSTRUMENTOS DA POLÍTICA URBANA")
    r.artigo("Para o cumprimento da função social da propriedade, o Município poderá aplicar os "
             "instrumentos previstos no Estatuto da Cidade (Lei Federal nº 10.257/2001):", [
                 "I - parcelamento, edificação ou utilização compulsórios;",
                 "II - IPTU progressivo no tempo, com alíquota majorada anualmente até o limite "
                 "de 15% (quinze por cento);",
                 "III - desapropriação com pagamento em títulos da dívida pública;",
                 "IV - direito de preempção;",
                 "V - transferência do direito de construir;",
                 "VI - operações urbanas consorciadas.",
             ])
    r.artigo("Considera-se subutilizado o lote com coeficiente de aproveitamento inferior a "
             "0,1 (um décimo) na Zona Central e na Zona Mista.")
    r.artigo("O proprietário notificado terá o prazo de 1 (um) ano para protocolar o projeto e "
             "de 2 (dois) anos, contados da aprovação, para iniciar as obras.")
    r.artigo("O direito de preempção vigorará pelo prazo de 5 (cinco) anos nas áreas definidas "
             "em lei específica.")

    r.capitulo("DA REGULARIZAÇÃO DE EDIFICAÇÕES")
    r.artigo("As edificações concluídas até a data de publicação desta Lei, em desacordo com "
             "seus parâmetros, poderão ser regularizadas mediante o pagamento de taxa.")
    r.artigo("Não serão regularizadas as edificações que avancem sobre o passeio público, áreas "
             "de preservação permanente ou faixas não edificáveis.")
    r.artigo("O pedido de regularização deverá ser protocolado em até 180 (cento e oitenta) "
             "dias da publicação desta Lei.")


def _condicoes_por_zona(r: _Redator, rng: random.Random) -> None:
    """Uma seção por zona, sem repetir os parâmetros do Anexo II (que valem sempre)."""
    r.capitulo("DAS CONDIÇÕES ESPECÍFICAS DE CADA ZONA")
    for codigo, nome, descricao in ZONAS:
        r.bloco("capitulo", f"Seção - {nome} ({codigo})")
        r.artigo(f"Na {codigo}, destinada a {descricao}, as novas edificações observarão as "
                 f"diretrizes de ocupação desta Seção, sem prejuízo dos parâmetros do Anexo II.")
        prazo = rng.choice([30, 45, 60])
        r.artigo(f"Na {codigo}, as atividades classificadas como permissíveis (C) dependerão "
                 f"de parecer do Conselho Municipal de Desenvolvimento Urbano, emitido no prazo "
                 f"de {prazo} ({por_extenso(prazo)}) dias.")
        diurno, noturno = rng.choice([50, 55, 60, 65]), rng.choice([40, 45, 50])
        r.artigo(f"Na {codigo}, o nível de ruído máximo admitido é de {diurno} dB(A) no período "
                 f"diurno e {noturno} dB(A) no período noturno, medido na divisa do lote.")
        r.artigo(f"Na {codigo}, as edificações destinadas a atividades não residenciais com área "
                 f"superior a {rng.choice([200, 300, 500])},00 m² deverão prever área de carga e "
                 f"descarga dentro do lote.")


def _anexo_afastamentos() -> list[list[str]]:
    linhas = [["Pavimentos", "Altura de referência H (m)", "Afastamento lateral (m)",
               "Afastamento de fundos (m)"]]
    for pavimentos in range(3, 21):
        altura = pavimentos * 3.0
        afastamento = max(1.5, altura / 6)
        linhas.append([str(pavimentos), formatar_numero(altura), formatar_numero(afastamento),
                       formatar_numero(afastamento)])
    return linhas


def _anexo_vias(rng: random.Random, fake: Faker) -> list[list[str]]:
    linhas = [["Via", "Classificação", "Largura total (m)", "Pista (m)", "Passeio (m)"]]
    for _ in range(36):
        classe, largura = rng.choice([("Arterial", 30.0), ("Coletora", 18.0), ("Local", 12.0)])
        linhas.append([f"{rng.choice(['Rua', 'Avenida', 'Alameda', 'Travessa'])} "
                       f"{fake.last_name()}", classe, formatar_numero(largura),
                       formatar_numero(largura - 5.0), formatar_numero(2.5)])
    return linhas


def _anexo_vagas(rng: random.Random) -> list[list[str]]:
    linhas = [["Atividade", "Vagas mínimas", "Vagas para carga e descarga"]]
    for atividade in _ATIVIDADES:
        base = rng.choice([25, 35, 50, 75, 100])
        linhas.append([atividade, f"1 vaga a cada {base},00 m² de área construída",
                       rng.choice(["dispensada", "1 vaga", "2 vagas"])])
    return linhas


def _anexo_atividades(rng: random.Random) -> list[list[str]]:
    linhas = [["Atividade", *[c for c, _, _ in ZONAS]]]
    for atividade in _ATIVIDADES:
        for porte in ("até 100 m²", "de 100 a 300 m²", "de 300 a 1.000 m²",
                      "acima de 1.000 m²"):
            linhas.append([f"{atividade} ({porte})",
                           *[rng.choice(["P", "P", "C", "N"]) for _ in ZONAS]])
    return linhas


def gerar_lei(projeto: Projeto) -> LeiMunicipal:
    rng = random.Random(projeto.semente * 83)
    fake = Faker("pt_BR")
    fake.seed_instance(projeto.semente * 83)
    ident = projeto.identificacao
    modelo = "A" if projeto.semente % 2 else "B"
    zona = rng.choice(ZONAS_RESIDENCIAIS)
    tabela = _parametros_das_zonas(projeto, zona, rng)
    numero_lei, ano = rng.randint(100, 499), rng.randint(2012, 2022)
    data = data_por_extenso(date(ano, rng.randint(1, 12), rng.randint(1, 28)))
    prefeito = f"{fake.first_name()} {fake.last_name()}"

    r = _Redator()
    tipo = "LEI COMPLEMENTAR" if modelo == "A" else "LEI"
    r.bloco("titulo", f"PREFEITURA MUNICIPAL DE {ident.municipio.upper()}")
    r.bloco("subtitulo", AVISO_FICTICIO)
    r.bloco("titulo", f"{tipo} Nº {numero_lei}, DE {data.upper()}")
    r.bloco("ementa", "Dispõe sobre o uso e a ocupação do solo urbano no Município de "
                      f"{ident.municipio}, estabelece o zoneamento e dá outras providências.")
    r.bloco("subtitulo", f"O PREFEITO MUNICIPAL DE {ident.municipio.upper()}, no uso de suas "
                         "atribuições, faz saber que a Câmara Municipal aprovou e ele sanciona a "
                         "seguinte Lei:")

    r.capitulo("DAS DISPOSIÇÕES PRELIMINARES")
    r.artigo("Esta Lei disciplina o uso e a ocupação do solo no território do Município, em "
             "conformidade com o Plano Diretor, observadas as normas federais e estaduais.")
    r.artigo("São objetivos desta Lei: ordenar o crescimento urbano, compatibilizar usos, "
             "garantir a qualidade ambiental e a função social da propriedade.")
    r.artigo("Para os fins desta Lei, adotam-se as seguintes definições:", _definicoes())

    r.capitulo("DO ZONEAMENTO")
    r.artigo("O território urbano fica dividido nas zonas abaixo, cujos perímetros estão "
             "descritos no Anexo I:",
             [f"{codigo} - {nome}: {descricao};" for codigo, nome, descricao in ZONAS])
    artigo_anexo = r.artigo("Os parâmetros urbanísticos de cada zona são os constantes do "
                            "Anexo II desta Lei.")
    for codigo, nome, descricao in ZONAS:
        r.artigo(f"A {nome} ({codigo}) destina-se predominantemente a {descricao}, sendo "
                 f"admitidas as atividades classificadas como permitidas (P) ou permissíveis "
                 f"(C) no Anexo III.")

    valor_antigo = None
    if modelo == "B":
        r.capitulo("DOS PARÂMETROS URBANÍSTICOS POR ZONA")
        for codigo, nome, _ in ZONAS:
            valores = tabela[codigo]
            itens = [f"{chr(97 + i)}) {rotulo.lower()}: {valor_texto(campo, valores[campo])};"
                     for i, (campo, rotulo, _) in enumerate(CAMPOS_LEI)]
            r.artigo(f"Na {nome} ({codigo}), ficam estabelecidos os seguintes parâmetros:",
                     itens)
        # Armadilha: artigo com redação alterada (o texto traz o valor antigo e o novo).
        atual = tabela[zona]["recuo_frontal_min"]
        antigo = atual + 1.0
        valor_antigo = ("recuo_frontal_min", antigo)
        r.artigo(f"Na {zona}, o recuo frontal mínimo será de {formatar_numero(atual)} m. "
                 f"(Redação dada pela Lei nº {numero_lei + rng.randint(5, 60)}, de "
                 f"{ano + rng.randint(1, 3)})")
        r.bloco("item", f"Redação anterior: \"Na {zona}, o recuo frontal mínimo será de "
                        f"{formatar_numero(antigo)} m.\"")

    _condicoes_por_zona(r, rng)
    r.capitulo("DAS DISPOSIÇÕES ESPECIAIS DE OCUPAÇÃO")
    r.artigo("Nos lotes de esquina, o recuo frontal mínimo será exigido em uma das testadas, "
             "admitindo-se recuo de 2,00 m (dois metros) na outra.")
    r.artigo("Nos lotes com testada inferior a 10,00 m (dez metros), o recuo lateral poderá ser "
             "dispensado em um dos lados, desde que não haja aberturas na parede da divisa.")
    r.artigo("A edícula poderá ocupar o recuo de fundos, desde que tenha altura máxima de "
             "4,00 m (quatro metros) e área de até 30% (trinta por cento) da edificação "
             "principal.")
    r.artigo("Os beirais com até 0,80 m (oitenta centímetros) não serão computados na taxa de "
             "ocupação nem nos recuos.")
    r.artigo("As piscinas descobertas não são computadas no coeficiente de aproveitamento, "
             "mas são consideradas área impermeável para o cálculo da taxa de permeabilidade.")
    r.artigo("Nos condomínios horizontais, os parâmetros desta Lei aplicam-se a cada unidade "
             "autônoma, sem prejuízo de restrições mais rigorosas previstas na convenção do "
             "condomínio, que não poderão contrariar esta Lei.")

    r.capitulo("DO LICENCIAMENTO")
    r.artigo("Nenhuma obra de construção, reforma ou ampliação poderá ser iniciada sem o "
             "respectivo alvará de construção, expedido pelo órgão municipal competente.")
    r.artigo("O pedido de alvará será instruído com os seguintes documentos:", [
        "I - requerimento assinado pelo proprietário ou seu procurador;",
        "II - certidão de inteiro teor da matrícula do imóvel, emitida há no máximo 30 (trinta) "
        "dias;",
        "III - projeto arquitetônico em 2 (duas) vias, assinado pelo proprietário e pelo autor;",
        "IV - Registro de Responsabilidade Técnica (RRT) ou Anotação de Responsabilidade "
        "Técnica (ART);",
        "V - memorial descritivo;",
        "VI - anuência do condomínio, quando for o caso.",
    ])
    r.artigo("O prazo para análise do pedido é de 30 (trinta) dias úteis, prorrogável uma vez "
             "por igual período.")
    r.artigo("O alvará de construção terá validade de 24 (vinte e quatro) meses, podendo ser "
             "renovado por mais 12 (doze) meses.")
    r.artigo("Concluída a obra, o proprietário requererá o habite-se, que será concedido após "
             "vistoria que comprove a conformidade com o projeto aprovado.")

    _capitulos_complementares(r)
    r.capitulo("DA FISCALIZAÇÃO E DAS PENALIDADES")
    r.artigo("A infração a esta Lei sujeita o infrator às seguintes penalidades:", [
        "I - advertência;",
        "II - multa de 50 (cinquenta) a 500 (quinhentas) Unidades Fiscais do Município (UFM);",
        "III - embargo da obra;",
        "IV - demolição das partes executadas em desacordo com a legislação.",
    ])
    ufm = rng.choice([42.5, 57.8, 63.1])
    r.artigo(f"O valor da UFM no exercício de {ano} é de R$ {formatar_numero(ufm)}, corrigido "
             f"anualmente.")
    r.artigo("Em caso de reincidência, a multa será aplicada em dobro.")

    r.capitulo("DAS DISPOSIÇÕES FINAIS")
    r.artigo("Os processos protocolados antes da vigência desta Lei serão analisados de acordo "
             "com a legislação anterior.")
    r.artigo("Esta Lei entra em vigor na data de sua publicação, revogadas as disposições em "
             "contrário.")
    r.bloco("subtitulo", f"Prefeitura Municipal de {ident.municipio}, {data}.")
    r.bloco("subtitulo", f"{prefeito.upper()} - Prefeito Municipal")

    # Anexo I: perímetros (a zona do projeto cita o condomínio)
    r.bloco("quebra")
    r.bloco("titulo", "ANEXO I - DESCRIÇÃO DOS PERÍMETROS DAS ZONAS")
    for codigo, nome, _ in ZONAS:
        lugares = [f"{rng.choice(['Loteamento', 'Jardim', 'Parque', 'Vila'])} "
                   f"{fake.last_name()}" for _ in range(rng.randint(2, 4))]
        if codigo == zona:
            lugares.insert(rng.randint(0, len(lugares)), ident.condominio)
        r.bloco("artigo", f"{codigo} - {nome}: compreende as áreas dos seguintes "
                          f"loteamentos e condomínios: {', '.join(lugares)}, e as áreas "
                          f"contíguas delimitadas no mapa de zoneamento.")

    # Anexo II: parâmetros em tabela
    r.bloco("quebra")
    r.bloco("titulo", "ANEXO II - PARÂMETROS URBANÍSTICOS POR ZONA")
    if modelo == "A":
        cabecalho = ["Zona", *[f"{rotulo} ({unidade})" if unidade else rotulo
                               for _, rotulo, unidade in CAMPOS_LEI]]
        linhas = [cabecalho]
        for codigo, _, _ in ZONAS:
            linhas.append([codigo, *[_numero_tabela(c, tabela[codigo][c])
                                     for c, _, _ in CAMPOS_LEI]])
    else:
        linhas = [["Parâmetro", *[c for c, _, _ in ZONAS]]]
        for campo, rotulo, unidade in CAMPOS_LEI:
            linhas.append([f"{rotulo} ({unidade})" if unidade else rotulo,
                           *[_numero_tabela(campo, tabela[c][campo]) for c, _, _ in ZONAS]])
    r.bloco("tabela", linhas=linhas)
    r.bloco("item", f"Notas: (1) ver exceções do Capítulo IV; (2) parâmetros referidos no "
                    f"art. {artigo_anexo}; (3) recuo 0,00 = dispensado.")

    r.bloco("quebra")
    r.bloco("titulo", "ANEXO III - CLASSIFICAÇÃO DAS ATIVIDADES POR ZONA")
    r.bloco("item", "P = permitida; C = permissível mediante consulta; N = não permitida.")
    r.bloco("tabela", linhas=_anexo_atividades(rng))
    r.bloco("quebra")
    r.bloco("titulo", "ANEXO IV - HIERARQUIA DO SISTEMA VIÁRIO")
    r.bloco("tabela", linhas=_anexo_vias(rng, fake))
    r.bloco("quebra")
    r.bloco("titulo", "ANEXO V - NÚMERO MÍNIMO DE VAGAS DE ESTACIONAMENTO")
    r.bloco("tabela", linhas=_anexo_vagas(rng))
    r.bloco("quebra")
    r.bloco("titulo", "ANEXO VI - AFASTAMENTOS PARA EDIFICAÇÕES COM MAIS DE 2 PAVIMENTOS")
    r.bloco("item", "Afastamento lateral e de fundos = H/6, com o mínimo de 1,50 m, em que H é "
                    "a altura da edificação. Não se aplica às edificações de até 2 pavimentos, "
                    "que seguem o Anexo II.")
    r.bloco("tabela", linhas=_anexo_afastamentos())
    r.bloco("quebra")
    r.bloco("titulo", "ANEXO VII - MAPA DE ZONEAMENTO (ESQUEMÁTICO)")
    r.bloco("mapa", f"{projeto.semente}")

    titulo = f"{tipo} {numero_lei}/{ano} - Uso e Ocupação do Solo - {ident.municipio}"
    return LeiMunicipal(DocumentoNormativo(titulo, r.blocos), modelo, zona, tabela, valor_antigo)


def _numero_tabela(campo: str, valor: float) -> str:
    if campo == "pavimentos_max":
        return str(int(valor))
    casas = 0 if campo in ("to_max", "permeavel_min") and valor == int(valor) else 2
    if campo == "ca_max":
        casas = 1 if round(valor, 1) == valor else 2
    return formatar_numero(valor, casas=casas)


# ---------------------------------------------------------------- norma do condomínio


@dataclass
class NormaCondominio:
    documento: DocumentoNormativo
    parametros: Parametros


def gerar_norma_condominio(projeto: Projeto) -> NormaCondominio:
    rng = random.Random(projeto.semente * 89)
    ident, c = projeto.identificacao, projeto.condominio
    r = _Redator()
    r.bloco("titulo", ident.condominio.upper())
    r.bloco("subtitulo", AVISO_FICTICIO)
    r.bloco("titulo", "REGULAMENTO DE OBRAS E EDIFICAÇÕES")
    r.bloco("ementa", "Aprovado em assembleia geral extraordinária, parte integrante da "
                      "convenção do condomínio.")

    r.capitulo("DAS DISPOSIÇÕES GERAIS")
    r.artigo("Este regulamento estabelece as normas para construção, reforma e ampliação das "
             "unidades autônomas, complementando a legislação municipal, que prevalece em caso "
             "de conflito.")
    r.artigo("Toda obra depende de aprovação prévia do projeto pela Comissão de Obras do "
             "condomínio, com antecedência mínima de 30 (trinta) dias do início.")

    r.capitulo("DOS PARÂMETROS CONSTRUTIVOS")
    if c.to_max is not None:
        r.artigo(f"A taxa de ocupação máxima de cada lote é de {valor_texto('to_max', c.to_max)}"
                 f" ({por_extenso(int(c.to_max))} por cento).")
    if c.recuo_frontal_min is not None:
        r.artigo(f"O recuo frontal mínimo é de {formatar_numero(c.recuo_frontal_min)} m, "
                 f"medido a partir do meio-fio da via interna.")
    if c.altura_max is not None:
        r.artigo(f"A altura máxima das edificações é de {formatar_numero(c.altura_max)} m, "
                 f"medida do nível do passeio ao ponto mais alto da cobertura.")
    r.artigo(f"Os muros de divisa entre lotes terão altura máxima de "
             f"{formatar_numero(c.muro_altura_max)} m, em alvenaria rebocada e pintada.")
    r.artigo("Na testada dos lotes é proibida a construção de muros, admitindo-se gradil ou "
             "cerca viva com altura de até 1,20 m (um metro e vinte centímetros).")
    r.artigo("É permitida a construção de no máximo 1 (uma) residência unifamiliar por lote, "
             "vedado o desmembramento.")
    r.artigo("As caixas d'água deverão ficar ocultas pela cobertura ou por platibanda.")

    r.capitulo("DA APROVAÇÃO DOS PROJETOS")
    r.artigo("O pedido de aprovação será instruído com os seguintes documentos:", [
        "I - projeto arquitetônico completo (situação, plantas, cortes e fachadas), em escala "
        "mínima de 1:100;",
        "II - memorial descritivo;",
        "III - RRT ou ART do autor do projeto;",
        "IV - comprovante de quitação das taxas condominiais;",
        "V - cópia da matrícula atualizada do lote.",
    ])
    r.artigo("A Comissão de Obras terá 15 (quinze) dias úteis para se manifestar, podendo "
             "solicitar adequações uma única vez.")
    r.artigo("A aprovação pelo condomínio não dispensa o alvará da Prefeitura, nem o "
             "atendimento à legislação municipal, que prevalece sobre este regulamento.")
    r.artigo("Qualquer alteração no projeto aprovado deverá ser submetida a nova aprovação.")

    r.capitulo("DO PAISAGISMO E DAS CALÇADAS")
    r.artigo("A calçada em frente a cada lote terá largura de 1,50 m (um metro e cinquenta "
             "centímetros), em piso intertravado, conforme padrão do condomínio.")
    r.artigo("Cada lote deverá ter, no mínimo, 1 (uma) árvore de médio porte na faixa frontal, "
             "de espécie constante da lista aprovada pelo condomínio.")
    r.artigo("É vedado o plantio de espécies cujas raízes possam danificar as redes de "
             "infraestrutura.")

    r.capitulo("DAS INSTALAÇÕES")
    r.artigo("As ligações de água, esgoto, energia e telefonia serão subterrâneas, a partir "
             "das caixas de passagem existentes na calçada.")
    r.artigo("É obrigatória a instalação de caixa de retenção de águas pluviais com volume "
             "mínimo de 1.000 (mil) litros.")
    r.artigo("Os aparelhos de ar-condicionado não poderão ser instalados na fachada voltada "
             "para a via interna.")

    r.capitulo("DA SEGURANÇA E DO ACESSO")
    r.artigo("O acesso de prestadores de serviço será feito exclusivamente pela portaria de "
             "serviço, mediante cadastro prévio.")
    r.artigo("Os veículos de carga com peso bruto superior a 12 (doze) toneladas dependem de "
             "autorização da administração.")
    r.artigo("A velocidade máxima nas vias internas é de 30 km/h (trinta quilômetros por "
             "hora).")

    r.capitulo("DA EXECUÇÃO DAS OBRAS")
    r.artigo("O horário de trabalho nas obras é de segunda a sexta-feira, das 8h às 17h, e aos "
             "sábados, das 8h às 12h.")
    r.artigo(f"O prazo máximo para conclusão da obra é de {rng.choice([24, 30, 36])} meses, "
             f"contados da aprovação do projeto.")
    r.artigo("O lote em obra deverá ser fechado com tapume de 2,20 m de altura na testada, "
             "removido ao fim da obra.")
    r.artigo("A caçamba de entulho deverá permanecer no interior do lote, sendo vedada sua "
             "colocação nas vias internas por mais de 24 (vinte e quatro) horas.")

    r.capitulo("DAS PENALIDADES")
    r.artigo(f"O descumprimento deste regulamento sujeita o condômino a multa equivalente a "
             f"{rng.choice([2, 5, 10])} (vezes) a taxa condominial vigente, dobrada na "
             f"reincidência, sem prejuízo do embargo da obra.")
    r.artigo("Este regulamento entra em vigor na data de sua aprovação.")
    sindico = Faker("pt_BR")
    sindico.seed_instance(projeto.semente * 89)
    aprovacao = date(2020 + rng.randint(0, 5), rng.randint(1, 12), rng.randint(1, 28))
    r.bloco("subtitulo", f"{ident.municipio}, {data_por_extenso(aprovacao)}.")
    r.bloco("subtitulo", f"{sindico.first_name()} {sindico.last_name()} - Síndico(a)")
    titulo = f"Regulamento de Obras - {ident.condominio}"
    return NormaCondominio(DocumentoNormativo(titulo, r.blocos), c)


# ---------------------------------------------------------------- PDF com texto


_ESTILOS = {
    "titulo": ParagraphStyle("t", fontName="VeraBd", fontSize=11.5, leading=15,
                             alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
    "subtitulo": ParagraphStyle("s", fontName="Vera", fontSize=9.5, leading=13,
                                alignment=TA_CENTER, spaceAfter=4),
    "ementa": ParagraphStyle("e", fontName="Vera", fontSize=9.5, leading=13, leftIndent=70 * mm,
                             alignment=TA_JUSTIFY, spaceAfter=8),
    "capitulo": ParagraphStyle("c", fontName="VeraBd", fontSize=10, leading=14,
                               alignment=TA_CENTER, spaceBefore=8, spaceAfter=4),
    "artigo": ParagraphStyle("a", fontName="Vera", fontSize=11, leading=15.5,
                             firstLineIndent=10 * mm, alignment=TA_JUSTIFY, spaceAfter=5),
    "item": ParagraphStyle("i", fontName="Vera", fontSize=11, leading=15.5, leftIndent=10 * mm,
                           alignment=TA_JUSTIFY, spaceAfter=3),
}


def _mapa_zoneamento(semente: int, largura: float) -> Drawing:
    """Quadras coloridas por zona, com o código da zona escrito (sem escala, fictício)."""
    rng = random.Random(semente)
    cores = {"ZR-1": "#f6e7a6", "ZR-2": "#f2d17c", "ZR-3": "#e8b85a", "ZM": "#f4a6a6",
             "ZC": "#e06c6c", "ZEIS": "#c9a3e0", "ZI": "#a9b7c9", "ZPA": "#9fd39b"}
    colunas, linhas = 9, 12
    passo = largura / colunas
    desenho = Drawing(largura, passo * linhas)
    for i in range(colunas):
        for j in range(linhas):
            zona = rng.choice(list(cores))
            x, y = i * passo, j * passo
            desenho.add(Rect(x + 2, y + 2, passo - 4, passo - 4, fillColor=HexColor(cores[zona]),
                             strokeColor=HexColor("#555555"), strokeWidth=0.4))
            desenho.add(String(x + passo / 2, y + passo / 2 - 3, zona, fontName="Vera",
                               fontSize=6.5, textAnchor="middle"))
    return desenho


def gerar_pdf_normativo(documento: DocumentoNormativo) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=25 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm, title=documento.titulo)
    elementos = []
    largura = A4[0] - 45 * mm
    for bloco in documento.blocos:
        if bloco.tipo == "quebra":
            elementos.append(PageBreak())
        elif bloco.tipo == "mapa":
            elementos.append(_mapa_zoneamento(int(bloco.texto), largura))
        elif bloco.tipo == "tabela":
            colunas = len(bloco.linhas[0])
            primeira = largura * (0.34 if colunas > 6 else 0.5)
            larguras = [primeira] + [(largura - primeira) / (colunas - 1)] * (colunas - 1)
            fonte = 6.5 if colunas > 8 else 8
            estilo_celula = ParagraphStyle("cel", fontName="Vera", fontSize=fonte,
                                           leading=fonte + 2, alignment=TA_CENTER)
            dados = [[Paragraph(celula, estilo_celula) for celula in linha]
                     for linha in bloco.linhas]
            tabela = Table(dados, colWidths=larguras, repeatRows=1)
            tabela.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, (0, 0, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), (0.88, 0.88, 0.88)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elementos += [Spacer(1, 2 * mm), tabela, Spacer(1, 3 * mm)]
        else:
            elementos.append(Paragraph(bloco.texto, _ESTILOS[bloco.tipo]))

    def rodape(canvas, doc_):
        canvas.setFont("Vera", 8)
        canvas.drawCentredString(A4[0] / 2, 10 * mm,
                                 f"{documento.titulo} - página {doc_.page} - DOCUMENTO FICTÍCIO")

    doc.build(elementos, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()


# ---------------------------------------------------------------- versão escaneada


ESTILO_NORMA_ESCANEADA = Estilo(fonte="times", formato="A4", cor_papel="branco",
                                corpo_pt=11.0, entrelinha_pt=14.5, margem_pt=60.0)


def gerar_norma_escaneada(documento: DocumentoNormativo, qualidade: str,
                          semente: int) -> DocumentoEscaneado:
    """Norma impressa e escaneada (tabelas viram linhas com colunas separadas por " | ")."""
    estilo = ESTILO_NORMA_ESCANEADA
    blocos: list[list[Linha]] = []
    for bloco in documento.blocos:
        if bloco.tipo in ("titulo", "capitulo"):
            blocos.append([Linha(bloco.texto, "centro", negrito=True)])
        elif bloco.tipo == "subtitulo":
            blocos.append([Linha(t, "centro") for t in _cortar(bloco.texto, estilo)])
        elif bloco.tipo == "tabela":
            blocos.append([Linha(" | ".join(linha)) for linha in bloco.linhas])
        elif bloco.tipo != "quebra":
            blocos.append(quebrar(bloco.texto, estilo,
                                  prefixo_negrito=len(bloco.texto.split(" ")[0]) + 2
                                  if bloco.texto.startswith("Art.") else 0))
    paginas = paginar(blocos, lambda _: [], estilo, moldura_no_cabecalho=False)
    paginas[-1].assinaturas = 1
    return gerar_pdf_escaneado(paginas, qualidade, semente, estilo)


def _cortar(texto: str, estilo: Estilo) -> list[str]:
    return [linha.texto.strip() for linha in quebrar(texto, estilo, recuo=0)]
