"""Especificação de um projeto sintético: a "verdade" de onde saem os PDFs e o gabarito.

Fluxo:  gerar_projeto_base(semente) → aplicar_erros(projeto, [...]) → gerar_gabarito(projeto)
                                                                → pranchas.gerar_pdfs(projeto)

O projeto base é sempre CONFORME (atende a todos os parâmetros, com folga). Cada erro injetado
altera uma coisa específica e produz exatamente um item "não atende"/"divergente" no gabarito.

Convenções (valem também para a Fase 4):
- Os documentos do AUTOR (pranchas e memorial) mostram os mesmos valores entre si.
- Matrícula e escritura mostram a verdade registral (ex.: área real do terreno).
- Índices declarados (TO, CA, TP) são calculados a partir dos valores IMPRESSOS na prancha;
  a conferência "declarado × recalculado" usa os valores da própria prancha.
- Hierarquia: a prefeitura prevalece sobre o condomínio (CLAUDE.md, princípio 7).
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field, fields

from faker import Faker

from arquiteto_auditor.avaliacao.gabarito import Gabarito

ELEMENTOS_COTAVEIS = (
    "testada", "profundidade_lote", "recuo_frontal", "recuo_fundos", "recuo_lateral_e",
    "recuo_lateral_d", "altura_total", "muro",
)

ERROS_DISPONIVEIS = (
    "area_terreno_divergente", "soma_areas_errada", "to_declarada_errada", "to_excedida",
    "recuo_frontal_insuficiente", "matricula_divergente", "revisao_divergente", "cota_omitida",
    "sem_norte", "sem_proprietario", "sem_assinatura_autor", "sem_assinatura_proprietario",
    "assinatura_alterada", "muro_alto", "altura_excedida",
)


# ---------------------------------------------------------------- estruturas


@dataclass
class Identificacao:
    titulo: str
    autor: str
    registro_autor: str
    rrt: str
    revisao: str
    endereco: str
    lote: str
    quadra: str
    condominio: str
    municipio: str
    matricula: str
    cartorio: str
    proprietario: str
    cpf_proprietario: str  # sempre INVÁLIDO (dígitos verificadores errados)
    escritorio: str


@dataclass
class Parametros:
    """Limites de uma fonte (prefeitura ou condomínio). None = a fonte não define."""

    lote_area_min: float | None = None
    testada_min: float | None = None
    recuo_frontal_min: float | None = None
    recuo_lateral_min: float | None = None
    recuo_fundos_min: float | None = None
    to_max: float | None = None
    ca_max: float | None = None
    permeavel_min: float | None = None
    altura_max: float | None = None
    pavimentos_max: int | None = None
    muro_altura_max: float | None = None


@dataclass
class Terreno:
    testada: float
    profundidade: float

    @property
    def area(self) -> float:
        return round(self.testada * self.profundidade, 2)


@dataclass
class Edificacao:
    largura: float
    profundidade: float
    recuo_frontal: float
    recuo_lateral_e: float
    areas_pavimentos: list[float]
    altura: float
    muro_altura: float
    area_permeavel: float

    @property
    def projecao(self) -> float:
        return round(self.largura * self.profundidade, 2)


@dataclass
class Apresentacao:
    """O que as pranchas MOSTRAM. None = mostra a verdade."""

    area_terreno: float | None = None
    area_total: float | None = None
    to_declarada: float | None = None
    matricula: str | None = None
    revisao_por_folha: dict[int, str] = field(default_factory=dict)
    mostrar_proprietario: bool = True
    mostrar_norte: bool = True
    cotas_omitidas: list[str] = field(default_factory=list)
    assinatura_autor: bool = True
    assinatura_proprietario: bool = True
    assinatura_alterada: bool = False


@dataclass
class Variacao:
    """Estilo visual das pranchas (não muda o conteúdo)."""

    estilo_carimbo: int  # 0 a 3
    estilo_quadro: int  # 0 a 3
    formato: str  # "A1", "A2", "A3"
    decimal_ponto: bool  # cotas "5.00" (estilo CAD) em vez de "5,00"
    cotas_rotuladas: bool  # "RECUO FRONTAL 5,00" ou só "5,00"
    caixa_alta: bool
    arquivo_unico: bool  # todas as folhas num PDF só, ou um PDF por folha
    estilo_software: str  # só influencia metadados e detalhes de texto
    estilo_norte: str = "seta"  # "seta" ou "rosa" (rosa dos ventos)


@dataclass
class Projeto:
    semente: int
    identificacao: Identificacao
    terreno: Terreno
    edificacao: Edificacao
    prefeitura: Parametros
    condominio: Parametros
    variacao: Variacao
    apresentacao: Apresentacao = field(default_factory=Apresentacao)
    erros: list[str] = field(default_factory=list)
    numero_folhas: int = 3

    # ------------------------------------------------ valores derivados (verdade)

    @property
    def recuo_lateral_d(self) -> float:
        e = self.edificacao
        return round(self.terreno.testada - e.recuo_lateral_e - e.largura, 2)

    @property
    def recuo_fundos(self) -> float:
        e = self.edificacao
        return round(self.terreno.profundidade - e.recuo_frontal - e.profundidade, 2)

    @property
    def area_total(self) -> float:
        return round(sum(self.edificacao.areas_pavimentos), 2)

    @property
    def to(self) -> float:
        return round(self.edificacao.projecao / self.terreno.area * 100, 2)

    @property
    def ca(self) -> float:
        return round(self.area_total / self.terreno.area, 2)

    @property
    def tp(self) -> float:
        return round(self.edificacao.area_permeavel / self.terreno.area * 100, 2)

    def parametro_adotado(self, nome: str) -> float | None:
        """A prefeitura prevalece; o condomínio vale quando a prefeitura não define."""
        valor = getattr(self.prefeitura, nome)
        return valor if valor is not None else getattr(self.condominio, nome)

    # ------------------------------------------------ o que a prancha mostra

    @property
    def area_terreno_prancha(self) -> float:
        a = self.apresentacao.area_terreno
        return self.terreno.area if a is None else a

    @property
    def area_total_prancha(self) -> float:
        a = self.apresentacao.area_total
        return self.area_total if a is None else a

    @property
    def to_prancha(self) -> float:
        if self.apresentacao.to_declarada is not None:
            return self.apresentacao.to_declarada
        return round(self.edificacao.projecao / self.area_terreno_prancha * 100, 2)

    @property
    def ca_prancha(self) -> float:
        return round(self.area_total_prancha / self.area_terreno_prancha, 2)

    @property
    def tp_prancha(self) -> float:
        return round(self.edificacao.area_permeavel / self.area_terreno_prancha * 100, 2)

    @property
    def matricula_prancha(self) -> str:
        return self.apresentacao.matricula or self.identificacao.matricula

    def revisao_da_folha(self, indice: int) -> str:
        return self.apresentacao.revisao_por_folha.get(indice, self.identificacao.revisao)


# ---------------------------------------------------------------- geração do projeto base


_LOGRADOUROS = ("Rua", "Alameda", "Avenida", "Travessa")
_NOMES_DE_RUA = ("das Acácias", "dos Ipês", "das Palmeiras", "dos Jacarandás", "das Orquídeas",
                 "dos Girassóis", "das Hortênsias", "dos Flamboyants", "das Magnólias")


_ESCRITORIOS = ("Estúdio", "Ateliê", "Oficina", "Grupo")


def cpf_invalido(rng: random.Random) -> str:
    """CPF com formato correto e dígitos verificadores ERRADOS: nunca coincide com um real.

    A verificação anti-vazamento (scripts/verificar_vazamento.py) bloqueia CPF válido.
    """
    base = [rng.randint(0, 9) for _ in range(9)]
    for posicao in (9, 10):
        soma = sum(base[i] * (posicao + 1 - i) for i in range(posicao))
        base.append((soma * 10) % 11 % 10)
    base[10] = (base[10] + 1 + rng.randint(0, 8)) % 10  # estraga o último dígito
    d = "".join(map(str, base))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _identificacao(semente: int, rng: random.Random) -> Identificacao:
    fake = Faker("pt_BR")
    fake.seed_instance(semente)

    def pessoa() -> str:  # sem títulos como "Dr." ou "Sra."
        return f"{fake.first_name()} {fake.last_name()} {fake.last_name()}"

    municipio = f"{rng.choice(['Vila', 'Nova', 'Porto', 'Campo', 'Serra'])} {fake.last_name()}"
    condominio = f"{rng.choice(['Residencial', 'Condomínio', 'Jardins do'])} {fake.last_name()}"
    numero_matricula = rng.randint(1_000, 99_999)
    return Identificacao(
        titulo=f"RESIDÊNCIA {fake.last_name().upper()}",
        autor=pessoa(),
        registro_autor=f"CAU A{rng.randint(10_000, 299_999)}-{rng.randint(0, 9)}",
        rrt=f"{rng.randint(10_000_000, 19_999_999)}",
        revisao="R00",
        endereco=f"{rng.choice(_LOGRADOUROS)} {rng.choice(_NOMES_DE_RUA)}, {rng.randint(10, 999)}",
        lote=str(rng.randint(1, 40)),
        quadra=rng.choice("ABCDEFGH"),
        condominio=condominio,
        municipio=municipio,
        matricula=f"{numero_matricula:,}".replace(",", "."),
        cartorio=f"{rng.randint(1, 3)}º Ofício de Registro de Imóveis de {municipio}",
        proprietario=pessoa(),
        cpf_proprietario=cpf_invalido(rng),
        escritorio=f"{rng.choice(_ESCRITORIOS)} {fake.last_name()} Arquitetura",
    )


def _parametros(rng: random.Random, terreno: Terreno) -> tuple[Parametros, Parametros]:
    prefeitura = Parametros(
        lote_area_min=rng.choice([200.0, 250.0, 300.0]),
        testada_min=rng.choice([8.0, 10.0, 12.0]),
        recuo_frontal_min=rng.choice([4.0, 5.0]),
        recuo_lateral_min=1.5,
        recuo_fundos_min=rng.choice([2.0, 3.0]),
        to_max=rng.choice([40.0, 45.0, 50.0]),
        ca_max=rng.choice([1.0, 1.2]),
        permeavel_min=rng.choice([15.0, 20.0]),
        altura_max=rng.choice([9.0, 10.0]),
        pavimentos_max=2,
    )
    # O condomínio repete alguns parâmetros (às vezes com valor diferente: conflito de
    # hierarquia) e é a única fonte da altura de muro.
    condominio = Parametros(muro_altura_max=rng.choice([1.8, 2.0, 2.2]))
    if rng.random() < 0.5:
        condominio.to_max = prefeitura.to_max - 5  # mais exigente, mas a prefeitura prevalece
    if rng.random() < 0.5:
        condominio.recuo_frontal_min = prefeitura.recuo_frontal_min
    if rng.random() < 0.3:
        condominio.altura_max = prefeitura.altura_max
    return prefeitura, condominio


def _variacao(rng: random.Random) -> Variacao:
    return Variacao(
        estilo_carimbo=rng.randrange(4),
        estilo_quadro=rng.randrange(4),
        formato=rng.choice(["A1", "A2", "A3"]),
        decimal_ponto=rng.random() < 0.3,
        cotas_rotuladas=rng.random() < 0.6,
        caixa_alta=rng.random() < 0.7,
        arquivo_unico=rng.random() < 0.5,
        estilo_software=rng.choice(["autocad", "revit", "archicad", "layout"]),
        estilo_norte=rng.choice(["seta", "rosa"]),
    )


def gerar_projeto_base(semente: int) -> Projeto:
    rng = random.Random(semente)
    identificacao = _identificacao(semente, rng)
    terreno = Terreno(
        testada=rng.choice([12.0, 12.5, 15.0, 16.0]),
        profundidade=rng.choice([30.0, 32.0, 35.0]),
    )
    prefeitura, condominio = _parametros(rng, terreno)
    projeto = Projeto(
        semente=semente,
        identificacao=identificacao,
        terreno=terreno,
        edificacao=Edificacao(0, 0, 0, 0, [], 0, 0, 0),
        prefeitura=prefeitura,
        condominio=condominio,
        variacao=_variacao(rng),
    )

    adotado = projeto.parametro_adotado
    lateral_e = adotado("recuo_lateral_min") + rng.choice([0.0, 0.25, 0.5])
    lateral_d = adotado("recuo_lateral_min") + rng.choice([0.0, 0.25, 0.5])
    largura = round(terreno.testada - lateral_e - lateral_d, 2)
    frontal = adotado("recuo_frontal_min") + rng.choice([0.0, 0.5, 1.0])

    to_alvo = adotado("to_max") - rng.choice([10.0, 12.0, 15.0])
    profundidade = round(terreno.area * to_alvo / 100 / largura, 2)
    profundidade_disponivel = terreno.profundidade - frontal - adotado("recuo_fundos_min") - 0.5
    profundidade = min(profundidade, round(profundidade_disponivel, 2))
    projecao = round(largura * profundidade, 2)

    permeavel = round(terreno.area * (adotado("permeavel_min") + rng.choice([5, 8, 10])) / 100, 2)
    muro_max = adotado("muro_altura_max")
    projeto.edificacao = Edificacao(
        largura=largura,
        profundidade=profundidade,
        recuo_frontal=frontal,
        recuo_lateral_e=lateral_e,
        areas_pavimentos=[projecao, round(projecao * 0.8, 2)],
        altura=rng.choice([6.5, 7.0, 7.5]),
        muro_altura=round(muro_max - rng.choice([0.0, 0.2]), 2),
        area_permeavel=permeavel,
    )
    return projeto


# ---------------------------------------------------------------- injeção de erros


def _proxima_revisao(codigo: str) -> str:
    return f"R{int(codigo[1:]) + 1:02d}"


def _alterar_matricula(numero: str) -> str:
    digitos = numero.replace(".", "")
    alterado = digitos[:-2] + digitos[-1] + digitos[-2]  # troca os dois últimos dígitos
    if alterado == digitos:
        alterado = digitos[:-1] + str((int(digitos[-1]) + 1) % 10)
    return f"{int(alterado):,}".replace(",", ".")


def _exceder_to(projeto: Projeto) -> None:
    """Aprofunda a edificação até a TO passar 2 p.p. do limite, mantendo os recuos mínimos."""
    adotado = projeto.parametro_adotado
    e, t = projeto.edificacao, projeto.terreno
    e.recuo_lateral_e = adotado("recuo_lateral_min")
    e.largura = round(t.testada - 2 * adotado("recuo_lateral_min"), 2)
    e.recuo_frontal = adotado("recuo_frontal_min")
    e.profundidade = round(t.area * (adotado("to_max") + 2) / 100 / e.largura + 0.01, 2)
    if projeto.recuo_fundos < adotado("recuo_fundos_min"):
        raise ValueError("to_excedida inviável neste terreno (recuo de fundos seria violado)")
    e.areas_pavimentos = [e.projecao, round(e.projecao * 0.8, 2)]


def aplicar_erros(projeto: Projeto, erros: list[str]) -> Projeto:
    projeto = copy.deepcopy(projeto)
    adotado = projeto.parametro_adotado
    a, e = projeto.apresentacao, projeto.edificacao
    for erro in erros:
        nome, _, argumento = erro.partition(":")
        if nome not in ERROS_DISPONIVEIS:
            raise ValueError(f"erro desconhecido: {erro!r}")
        if nome == "area_terreno_divergente":
            a.area_terreno = round(projeto.terreno.area - 2.30, 2)
        elif nome == "soma_areas_errada":
            a.area_total = round(projeto.area_total + 10.0, 2)
        elif nome == "to_declarada_errada":
            a.to_declarada = round(projeto.to + 4.0, 2)
        elif nome == "to_excedida":
            _exceder_to(projeto)
        elif nome == "recuo_frontal_insuficiente":
            e.recuo_frontal = round(adotado("recuo_frontal_min") - 0.5, 2)
        elif nome == "matricula_divergente":
            a.matricula = _alterar_matricula(projeto.identificacao.matricula)
        elif nome == "revisao_divergente":
            a.revisao_por_folha[1] = _proxima_revisao(projeto.identificacao.revisao)
        elif nome == "cota_omitida":
            if argumento not in ELEMENTOS_COTAVEIS:
                raise ValueError(f"elemento de cota desconhecido: {argumento!r}")
            a.cotas_omitidas.append(argumento)
        elif nome == "sem_norte":
            a.mostrar_norte = False
        elif nome == "sem_proprietario":
            a.mostrar_proprietario = False
        elif nome == "sem_assinatura_autor":
            a.assinatura_autor = False
        elif nome == "sem_assinatura_proprietario":
            a.assinatura_proprietario = False
        elif nome == "assinatura_alterada":
            a.assinatura_alterada = True
        elif nome == "muro_alto":
            e.muro_altura = round(adotado("muro_altura_max") + 0.4, 2)
        elif nome == "altura_excedida":
            e.altura = round(adotado("altura_max") + 0.5, 2)
        projeto.erros.append(erro)
    return projeto


# ---------------------------------------------------------------- gabarito


_PARAMETROS = {
    # chave do catálogo: (nome do parâmetro, tipo de limite, valor do projeto, cota necessária)
    "LOTE_AREA_MIN": ("lote_area_min", "minimo", lambda p: p.terreno.area, None),
    "LOTE_TESTADA_MIN": ("testada_min", "minimo", lambda p: p.terreno.testada, "testada"),
    "RECUO_FRONTAL": ("recuo_frontal_min", "minimo", lambda p: p.edificacao.recuo_frontal,
                      "recuo_frontal"),
    "RECUO_LATERAL_E": ("recuo_lateral_min", "minimo", lambda p: p.edificacao.recuo_lateral_e,
                        "recuo_lateral_e"),
    "RECUO_LATERAL_D": ("recuo_lateral_min", "minimo", lambda p: p.recuo_lateral_d,
                        "recuo_lateral_d"),
    "RECUO_FUNDOS": ("recuo_fundos_min", "minimo", lambda p: p.recuo_fundos, "recuo_fundos"),
    "TO_MAX": ("to_max", "maximo", lambda p: p.to, None),
    "CA_MAX": ("ca_max", "maximo", lambda p: p.ca, None),
    "PERMEAVEL_MIN": ("permeavel_min", "minimo", lambda p: p.tp, None),
    "ALTURA_MAX": ("altura_max", "maximo", lambda p: p.edificacao.altura, "altura_total"),
    "PAVIMENTOS_MAX": ("pavimentos_max", "maximo",
                       lambda p: len(p.edificacao.areas_pavimentos), None),
    "MURO_ALTURA_MAX": ("muro_altura_max", "maximo", lambda p: p.edificacao.muro_altura, "muro"),
}


def _item(chave, status, escopo=None, **extras) -> dict:
    item = {"chave": chave, "status": status}
    if escopo:
        item["escopo"] = escopo
    return item | {k: v for k, v in extras.items() if v is not None}


def _status_igual(condicao_ok: bool) -> str:
    return "atende" if condicao_ok else "divergente"


def gerar_gabarito(projeto: Projeto, conjunto: str, rodada: str = "R00",
                   conjunto_anterior: str | None = None) -> Gabarito:
    p, a, ident = projeto, projeto.apresentacao, projeto.identificacao
    omitidas = set(a.cotas_omitidas)
    itens: list[dict] = []
    valores: dict[str, dict] = {}

    # Identificação
    itens.append(_item("ID_MATRICULA", _status_igual(p.matricula_prancha == ident.matricula),
                       documentos=["prancha", "matricula"] if a.matricula else None))
    revisoes = {p.revisao_da_folha(i) for i in range(p.numero_folhas)}
    itens.append(_item("ID_REVISAO", _status_igual(len(revisoes) == 1)))
    for chave in ("ID_CARTORIO", "ID_LOTE_QUADRA", "ID_CONDOMINIO", "ID_ENDERECO",
                  "ID_AUTOR_REGISTRO", "ID_RRT_ART"):
        itens.append(_item(chave, "atende"))
    itens.append(_item("ID_PROPRIETARIO", "atende" if a.mostrar_proprietario else "nao_atende"))

    # Consistência entre documentos (memorial acompanha a prancha; matrícula = verdade)
    itens.append(_item("TERRENO_AREA",
                       _status_igual(abs(p.area_terreno_prancha - p.terreno.area) < 0.005),
                       documentos=["prancha", "matricula"] if a.area_terreno else None))
    valores["TERRENO_AREA"] = {"prancha": p.area_terreno_prancha, "matricula": p.terreno.area}
    itens.append(_item("TERRENO_TESTADA",
                       "nao_verificavel" if "testada" in omitidas else "atende"))
    for indice in range(1, len(p.edificacao.areas_pavimentos) + 1):
        itens.append(_item("AREA_CONSTR_PAV", "atende", escopo=f"pavimento={indice}"))
    itens.append(_item("AREA_CONSTR_TOTAL", "atende"))
    valores["AREA_CONSTR_TOTAL"] = {"prancha": p.area_total_prancha, "calculado": p.area_total}

    # Aritmética da própria prancha
    itens.append(_item("AREA_CONSTR_SOMA",
                       _status_igual(abs(p.area_total_prancha - p.area_total) < 0.005)))
    to_recalculada = round(p.edificacao.projecao / p.area_terreno_prancha * 100, 2)
    itens.append(_item("TO_DECLARADA", _status_igual(abs(p.to_prancha - to_recalculada) < 0.01),
                       valor_projeto=p.to_prancha if a.to_declarada else None))
    itens.append(_item("CA_DECLARADO", "atende"))
    itens.append(_item("PERMEAVEL_DECLARADA", "atende"))

    # Parâmetros
    for chave, (nome, limite_tipo, valor_de, cota) in _PARAMETROS.items():
        limite = p.parametro_adotado(nome)
        valor = valor_de(p)
        fontes = {"prefeitura": getattr(p.prefeitura, nome),
                  "condominio": getattr(p.condominio, nome), "adotado": limite}
        valores[chave] = {k: v for k, v in fontes.items() if v is not None} | {"calculado": valor}
        if cota in omitidas or limite is None:
            itens.append(_item(chave, "nao_verificavel"))
            continue
        ok = valor >= limite - 1e-9 if limite_tipo == "minimo" else valor <= limite + 1e-9
        itens.append(_item(chave, "atende" if ok else "nao_atende",
                           valor_projeto=None if ok else valor, limite=None if ok else limite))

    # Completude
    itens.append(_item("NORTE_INDICADO", "atende" if a.mostrar_norte else "nao_atende"))
    itens.append(_item("ASSINATURA_AUTOR", "atende" if a.assinatura_autor else "nao_atende"))
    itens.append(_item("ASSINATURA_PROPRIETARIO",
                       "atende" if a.assinatura_proprietario else "nao_atende"))
    if not (a.assinatura_autor or a.assinatura_proprietario):
        digital = "nao_verificavel"
    else:
        digital = "nao_atende" if a.assinatura_alterada else "atende"
    itens.append(_item("ASSINATURA_DIGITAL_VALIDA", digital))
    for elemento in sorted(omitidas):
        itens.append(_item("COTA_INDEFINIDA", "nao_atende", escopo=f"elemento={elemento}"))

    return Gabarito.model_validate({
        "conjunto": conjunto,
        "versao_gabarito": 1,
        "rodada": rodada,
        "conjunto_anterior": conjunto_anterior,
        "descricao": "Erros injetados: " + (", ".join(p.erros) or "nenhum (conjunto limpo)"),
        "valores_esperados": valores,
        "itens_esperados": itens,
    })


def como_dicionario(projeto: Projeto) -> dict:
    """Especificação completa em formato JSON (inclui valores derivados, para conferência)."""
    def converter(objeto):
        if hasattr(objeto, "__dataclass_fields__"):
            return {f.name: converter(getattr(objeto, f.name)) for f in fields(objeto)}
        if isinstance(objeto, list):
            return [converter(x) for x in objeto]
        if isinstance(objeto, dict):
            return {str(k): converter(v) for k, v in objeto.items()}
        return objeto

    dados = converter(projeto)
    dados["derivados"] = {
        "area_terreno": projeto.terreno.area, "projecao": projeto.edificacao.projecao,
        "recuo_lateral_d": projeto.recuo_lateral_d, "recuo_fundos": projeto.recuo_fundos,
        "area_total": projeto.area_total, "to": projeto.to, "ca": projeto.ca, "tp": projeto.tp,
    }
    return dados
