"""Escritura pública de compra e venda fictícia, escaneada em papel de segurança.

A escritura é a da venda ao proprietário ATUAL (último "R- COMPRA E VENDA" da matrícula) e é
coerente com o registro: mesmas partes, CPFs, valor, data, livro e folhas.

Armadilha realista (Fase 7): a escritura descreve o imóvel como ele estava NA DATA DA VENDA.
Se a matrícula teve uma retificação de área depois, a área da escritura é a antiga; a verdade
atual está só na matrícula.

Estilo calibrado com um exemplo real (docs/06-calibracao-exemplos-reais.md §5): folha Carta,
impressão a laser, papel de segurança (brasão-marca-d'água amarelo, fibras), faixa no topo da
1ª página, título e livro/folhas em caixas com moldura, rubrica na margem direita e fecho com
assinaturas, carimbos e selo.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from faker import Faker

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
from dados_sinteticos.geradores.especificacao import Projeto
from dados_sinteticos.geradores.registro import (
    AVISO_FICTICIO,
    Matricula,
    Venda,
    _codigo_selo,
    _descricao_lote,
    br,
    data_por_extenso,
    gerar_matricula,
    por_extenso,
)

ESTILO_ESCRITURA = Estilo(fonte="arial", formato="carta", cor_papel="branco",
                          papel_seguranca=True, corpo_pt=12.0, entrelinha_pt=15.0,
                          margem_pt=48.0)


@dataclass
class Escritura:
    venda: Venda
    tabelionato: str
    tabeliao: str
    escrevente: str
    endereco: str
    protocolo: int
    itbi_guia: int
    emolumentos: float
    selo: str

    @property
    def folhas_ate(self) -> int:
        return self.venda.folhas + 3


def gerar_escritura(projeto: Projeto, matricula: Matricula) -> Escritura:
    rng = random.Random(projeto.semente * 53)
    fake = Faker("pt_BR")
    fake.seed_instance(projeto.semente * 53)
    municipio = projeto.identificacao.municipio
    return Escritura(
        venda=matricula.vendas[-1],
        tabelionato=f"{rng.randint(1, 4)}º Tabelionato de Notas de {municipio}",
        tabeliao=f"{fake.first_name()} {fake.last_name()} {fake.last_name()}",
        escrevente=f"{fake.first_name()} {fake.last_name()}",
        endereco=f"{fake.street_prefix()} {fake.last_name()}, {rng.randint(10, 999)}, Centro",
        protocolo=rng.randint(10_000, 99_999),
        itbi_guia=rng.randint(100_000, 999_999),
        emolumentos=rng.randint(1_500, 4_500) + rng.randint(0, 99) / 100,
        selo=_codigo_selo(rng),
    )


def paragrafos_da_escritura(e: Escritura, projeto: Projeto, m: Matricula) -> list[str]:
    v, ident = e.venda, projeto.identificacao
    imovel = _descricao_lote(projeto, v.testada, v.profundidade, v.area)
    itbi = round(v.valor * 0.02, 2)
    return [
        f"SAIBAM quantos esta pública escritura de compra e venda virem que, aos "
        f"{data_por_extenso(v.data_escritura)}, nesta cidade de {ident.municipio}, Estado de "
        f"{m.estado}, neste {e.tabelionato}, perante mim, {e.escrevente}, Escrevente "
        f"Autorizado(a), compareceram as partes entre si justas e contratadas, a saber:",
        f"OUTORGANTE VENDEDOR(A): {v.vendedor.qualificacao(ident.municipio)}.",
        f"OUTORGADO(A) COMPRADOR(A): {v.comprador.qualificacao(ident.municipio)}.",
        "Os presentes, reconhecidos como os próprios por mim, à vista dos documentos de "
        "identificação apresentados, do que dou fé. E, pelo(a) outorgante vendedor(a), me foi "
        "dito:",
        f"DO IMÓVEL: Que é senhor(a) e legítimo(a) possuidor(a) do seguinte imóvel: {imovel} "
        f"Imóvel matriculado sob nº {m.numero} no {m.cartorio}.",
        f"DO PREÇO: Que, pela presente escritura e na melhor forma de direito, vende o imóvel "
        f"descrito ao(à) outorgado(a) comprador(a), pelo preço certo e ajustado de "
        f"R$ {br(v.valor)} ({por_extenso(v.valor)} reais), pago neste ato, do qual dá plena "
        f"e geral quitação.",
        f"DO IMPOSTO DE TRANSMISSÃO: Foi apresentada a guia de ITBI nº {e.itbi_guia}, emitida "
        f"pela Prefeitura Municipal de {ident.municipio}, no valor de R$ {br(itbi)}, "
        f"devidamente quitada.",
        f"DAS CERTIDÕES: Foram apresentadas a certidão de ônus reais e a certidão de ações "
        f"reais e pessoais reipersecutórias relativas ao imóvel, expedidas pelo {m.cartorio}, "
        f"e a certidão negativa de débitos municipais, que ficam arquivadas neste "
        f"Tabelionato. Será emitida a Declaração sobre Operação Imobiliária (DOI).",
        "DA POSSE E DO DOMÍNIO: Que, por força desta escritura, transmite ao(à) outorgado(a) "
        "comprador(a) toda a posse, domínio, direito e ação que exercia sobre o imóvel, "
        "obrigando-se por si, seus herdeiros e sucessores, a fazer esta venda sempre boa, firme "
        "e valiosa, e a responder pela evicção de direito, na forma da lei.",
        "DOS ÔNUS: Declara o(a) outorgante vendedor(a), sob as penas da lei, que o imóvel se "
        "encontra livre e desembaraçado de quaisquer ônus reais, judiciais ou extrajudiciais, "
        "dívidas e impostos de qualquer natureza, e que não existem contra si ações reais ou "
        "pessoais reipersecutórias relativas ao imóvel.",
        f"DA INDISPONIBILIDADE DE BENS: Foi consultada a Central Nacional de Indisponibilidade "
        f"de Bens, com resultado negativo para o(a) outorgante vendedor(a), conforme código "
        f"de consulta {e.protocolo * 7}.",
        f"DO CONDOMÍNIO: Foi apresentada declaração de quitação das contribuições "
        f"condominiais, emitida pela administração do {ident.condominio}, que fica arquivada "
        f"neste Tabelionato.",
        f"DAS DECLARAÇÕES: O(A) outorgado(a) comprador(a) declara conhecer e aceitar a "
        f"convenção e o regulamento interno do {ident.condominio}. As partes autorizam o "
        f"Oficial do Registro de Imóveis competente a proceder ao registro desta escritura.",
        f"E, por estarem assim justos e contratados, pediram-me que lavrasse esta escritura, "
        f"que, feita e lida em voz alta, foi achada conforme, aceitam e assinam. Eu, "
        f"{e.escrevente}, Escrevente Autorizado(a), a digitei. Eu, {e.tabeliao}, Tabelião, a "
        f"subscrevo e assino. Emolumentos: R$ {br(e.emolumentos)}. Selo: {e.selo}.",
    ]


def _rotulo(paragrafo: str) -> int:
    """Rótulos em caixa alta no início ("OUTORGANTE VENDEDOR(A):", "DO PREÇO:")."""
    cabeca, separador, _ = paragrafo.partition(":")
    return len(cabeca) + 1 if separador and cabeca.isupper() and len(cabeca) < 40 else 0


def paginas_da_escritura(e: Escritura, projeto: Projeto, m: Matricula) -> list[Pagina]:
    estilo = ESTILO_ESCRITURA
    v = e.venda

    def cabecalho(numero_pagina: int) -> list[Linha]:
        if numero_pagina > 1:
            return [Linha("", brasao=True, escala=2.5),
                    Linha(e.tabelionato.upper(), "centro", negrito=True),
                    Linha(f"Livro {v.livro} - Folha {v.folhas + numero_pagina - 1}", "centro"),
                    Linha(AVISO_FICTICIO, "centro")]
        return [
            Linha(e.tabelionato.upper(), "centro", negrito=True, escala=1.3),
            Linha(f"Tabelião: {e.tabeliao}", "centro"),
            Linha(f"{e.endereco} - {projeto.identificacao.municipio} - {m.estado}", "centro"),
            Linha(AVISO_FICTICIO, "centro"),
            Linha(""),
            Linha("ESCRITURA PÚBLICA DE COMPRA E VENDA", "centro", negrito=True),
            Linha(""),
            Linha(f"LIVRO {v.livro} - FOLHAS {v.folhas}/{e.folhas_ate} - PROTOCOLO "
                  f"{e.protocolo}", "centro", negrito=True),
            Linha(f"VALOR: R$ {br(v.valor)}", "centro"),
        ]

    blocos = [quebrar(p, estilo, prefixo_negrito=_rotulo(p))
              for p in paragrafos_da_escritura(e, projeto, m)]
    fecho = [Linha(f"{projeto.identificacao.municipio}, {data_por_extenso(v.data_escritura)}.",
                   "centro"),
             Linha(""),
             Linha("OUTORGANTE VENDEDOR(A) - OUTORGADO(A) COMPRADOR(A) - TABELIÃO", "centro")]
    blocos.append(fecho)
    paginas = paginar(blocos, cabecalho, estilo, reserva_final=12, moldura_no_cabecalho=False)
    paginas[0].faixa_topo = True
    paginas[0].molduras = [(5, 6), (7, 8)]  # título e livro/folhas em caixas
    for numero, pagina in enumerate(paginas, start=1):
        pagina.rubrica_margem = True
        pagina.cor_papel = "branco" if numero % 2 else "amarelado"
    ultima = paginas[-1]
    ultima.assinaturas = 3
    ultima.carimbos = [Carimbo([e.tabelionato.upper()[:18], "FICTÍCIO", "TABELIÃO"]),
                       Carimbo(["CONFERE COM", "O ORIGINAL", f"PROT. {e.protocolo}"],
                               redondo=False)]
    ultima.selo = e.selo
    return paginas


def gerar_escritura_escaneada(projeto: Projeto, qualidade: str,
                              matricula: Matricula | None = None
                              ) -> tuple[Escritura, DocumentoEscaneado]:
    matricula = matricula or gerar_matricula(projeto)
    escritura = gerar_escritura(projeto, matricula)
    semente = projeto.semente * 59
    paginas = paginas_da_escritura(escritura, projeto, matricula)
    return escritura, gerar_pdf_escaneado(paginas, qualidade, semente, ESTILO_ESCRITURA)
