"""Documentos "escaneados" fictícios: texto → página desenhada → imagem degradada → PDF sem texto.

Usado para matrículas, escrituras e memoriais escaneados. O PDF final só tem imagens (como um
scanner de verdade); o texto de cada página é devolvido à parte, como "verdade" para medir o
OCR na Fase 5 (a verdade não inclui carimbos, selos, assinaturas nem o carimbo "CÓPIA").

Estilos (calibrados com exemplos reais, docs/06-calibracao-exemplos-reais.md §5):
- impressão: máquina de escrever (Courier, letras tremidas) ou laser (Arial/Times, uniforme);
- folha A4 ou Carta; papel comum ou papel de segurança (cor de fundo, brasão-marca-d'água,
  fibras coloridas, faixas de segurança nas bordas);
- elementos de cartório: brasão no cabeçalho, caixas com moldura, rótulos em negrito, rubrica
  na margem, riscos diagonais anulando o espaço em branco, carimbos, selo com QR code,
  carimbo "CÓPIA" repetido e verso em branco com o texto da frente transparecendo.

Degradação (Pillow + numpy, sem dependências extras): papel manchado, tinta desbotada,
sujeira, inclinação, desfoque, ruído e compressão JPEG. Três qualidades: "boa" (escaneamento
de mesa limpo, o caso típico), "media" e "ruim" (testes de resistência do OCR).
"""

from __future__ import annotations

import io
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

import numpy as np
import pymupdf
import reportlab
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_PASTA_FONTES = Path(reportlab.__file__).parent / "fonts"
# Fontes Type 1 que acompanham o reportlab (com acentos): (normal, negrito).
FONTES = {
    "courier": (_PASTA_FONTES / "com_____.pfb", _PASTA_FONTES / "cob_____.pfb"),  # máquina
    "arial": (_PASTA_FONTES / "_a______.pfb", _PASTA_FONTES / "_ab_____.pfb"),
    "times": (_PASTA_FONTES / "_er_____.pfb", _PASTA_FONTES / "_eb_____.pfb"),
}
FORMATOS_PT = {"A4": (595.0, 842.0), "carta": (612.0, 792.0)}
CORES_PAPEL = {
    "branco": (253, 254, 250),
    "amarelado": (250, 245, 222),
    "azulado": (246, 250, 253),
    "envelhecido": (246, 240, 222),
}

TINTA_PRETA = (25, 25, 30)
TINTA_AZUL = (30, 50, 150)
TINTA_CARIMBO = ((40, 60, 160), (150, 30, 40), (60, 60, 60))  # azul, vermelho, preto
TINTA_COPIA = (55, 45, 70)
COR_MARCA_DAGUA = (222, 205, 125)
COR_FAIXA_ESQUERDA = (70, 72, 80)
COR_FAIXA_DIREITA = (45, 115, 95)
CORES_FIBRAS = ((200, 70, 80), (90, 110, 200), (220, 130, 150))


@dataclass(frozen=True)
class Qualidade:
    nome: str
    dpi: int
    inclinacao_max: float  # graus (sorteada entre -max e +max)
    ruido: float  # desvio-padrão do ruído, em tons de 0 a 255
    desfoque: float  # raio do desfoque gaussiano, em pixels
    jpeg: int  # qualidade da compressão JPEG (0 a 100)
    sujeira: int  # pontos de sujeira por página
    desbotamento: float  # 0 = tinta forte; 1 = tinta some
    colorido: bool


QUALIDADES: dict[str, Qualidade] = {
    "boa": Qualidade("boa", 300, 0.4, 3.0, 0.0, 70, 10, 0.0, True),
    "media": Qualidade("media", 200, 1.8, 8.0, 0.5, 65, 120, 0.2, True),
    "ruim": Qualidade("ruim", 150, 3.0, 14.0, 0.7, 45, 300, 0.35, False),
}


@dataclass(frozen=True)
class Estilo:
    fonte: str = "courier"  # "courier" (máquina de escrever), "arial" ou "times" (laser)
    formato: str = "A4"  # "A4" ou "carta"
    cor_papel: str = "envelhecido"  # chave de CORES_PAPEL
    papel_seguranca: bool = False  # brasão-marca-d'água e fibras coloridas
    faixas_borda: bool = False  # faixas de segurança nas bordas (só na frente da folha)
    corpo_pt: float = 10.5  # tamanho da letra
    entrelinha_pt: float = 14.5
    margem_pt: float = 56.0

    @property
    def maquina(self) -> bool:
        return self.fonte == "courier"

    @property
    def tamanho_pt(self) -> tuple[float, float]:
        return FORMATOS_PT[self.formato]

    @property
    def largura_texto_pt(self) -> float:
        extra = 30.0 if self.faixas_borda else 0.0  # as faixas tomam parte da folha
        return self.tamanho_pt[0] - 2 * self.margem_pt - extra

    @property
    def x_texto_pt(self) -> float:
        return self.margem_pt + (24.0 if self.faixas_borda else 0.0)

    @property
    def linhas_por_pagina(self) -> float:
        return (self.tamanho_pt[1] - 2 * self.margem_pt) / self.entrelinha_pt

    def medir(self, texto: str, negrito: bool = False, escala: float = 1.0) -> float:
        """Largura do texto em pontos."""
        if self.maquina:
            return len(texto) * 0.6 * self.corpo_pt * escala
        return _fonte(self.fonte, negrito, 1000).getlength(texto) * self.corpo_pt * escala / 1000


ESTILO_PADRAO = Estilo()  # máquina de escrever em A4 (imutável: pode ser valor padrão)


@cache
def _fonte(nome: str, negrito: bool, tamanho_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTES[nome][1 if negrito else 0]), tamanho_px)


# ---------------------------------------------------------------- diagramação


@dataclass
class Linha:
    texto: str
    alinhamento: str = "esquerda"  # "esquerda", "centro" ou "justificado"
    negrito: bool = False
    escala: float = 1.0  # títulos maiores (a linha ocupa `escala` entrelinhas)
    prefixo_negrito: int = 0  # os N primeiros caracteres em negrito (rótulo "R-1/...")
    brasao: bool = False  # em vez de texto, um brasão redondo centralizado
    assinar: bool = False  # assinatura à caneta sobre esta linha ("____")

    @property
    def texto_limpo(self) -> str:
        return " ".join(self.texto.split())


@dataclass
class Carimbo:
    linhas: list[str]
    redondo: bool = True


@dataclass
class Pagina:
    linhas: list[Linha]
    molduras: list[tuple[int, int]] = field(default_factory=list)  # linhas [início, fim)
    carimbos: list[Carimbo] = field(default_factory=list)
    selo: str | None = None  # código do selo (desenhado com um "QR" fictício)
    assinaturas: int = 0  # assinaturas grandes no pé da página
    rubricas_apos: str | None = None  # rubrica depois das linhas que terminam assim
    rubrica_margem: bool = False  # rubrica do tabelião na margem direita
    anular_espaco: bool = False  # riscos diagonais no espaço em branco depois do texto
    copias: int = 0  # quantas vezes o carimbo "CÓPIA" aparece
    verso: bool = False  # verso da folha (o texto da frente transparece)
    faixa_topo: bool = False  # faixa escura com emblemas no topo (1ª página da escritura)
    cor_papel: str | None = None  # substitui a cor do estilo nesta página

    @property
    def texto(self) -> str:
        """Texto impresso da página (verdade para o OCR), uma linha por linha."""
        return "\n".join(linha.texto_limpo for linha in self.linhas
                         if linha.texto_limpo and not linha.brasao)


def quebrar(paragrafo: str, estilo: Estilo = ESTILO_PADRAO, recuo: int = 4,
            prefixo_negrito: int = 0) -> list[Linha]:
    """Quebra um parágrafo em linhas justificadas (a última fica alinhada à esquerda).

    `prefixo_negrito` põe em negrito os N primeiros caracteres do parágrafo (um rótulo).
    """
    limite = estilo.largura_texto_pt * 0.98  # folga para o negrito, que é mais largo
    linhas: list[str] = []
    atual = " " * recuo
    for palavra in paragrafo.split():
        candidato = f"{atual} {palavra}" if atual.strip() else atual + palavra
        if atual.strip() and estilo.medir(candidato) > limite:
            linhas.append(atual)
            atual = palavra
        else:
            atual = candidato
    linhas.append(atual)
    resultado = [Linha(t, "justificado") for t in linhas]
    resultado[-1].alinhamento = "esquerda"
    resultado[0].prefixo_negrito = prefixo_negrito + recuo if prefixo_negrito else 0
    return resultado


def paginar(blocos: list[list[Linha]], cabecalho: Callable[[int], list[Linha]],
            estilo: Estilo = ESTILO_PADRAO, reserva_final: int = 0,
            moldura_no_cabecalho: bool = True) -> list[Pagina]:
    """Distribui blocos de linhas em páginas.

    `cabecalho(n)` dá as linhas que abrem a página n (1, 2...).
    `reserva_final` deixa N linhas livres no fim da última página (carimbos, assinatura).
    """
    limite = estilo.linhas_por_pagina
    paginas: list[Pagina] = []

    def ocupado() -> float:
        return sum(linha.escala for linha in paginas[-1].linhas)

    def nova() -> None:
        topo = cabecalho(len(paginas) + 1)
        molduras = [(0, len(topo))] if moldura_no_cabecalho else []
        paginas.append(Pagina([*topo, Linha("")], molduras=molduras))

    nova()
    for numero, bloco in enumerate(blocos, start=1):
        linhas = [*bloco, Linha("")]
        ultimo = numero == len(blocos)
        if ultimo and ocupado() + len(linhas) > limite - reserva_final:
            nova()  # o último bloco vai inteiro para a página nova, com o espaço reservado
        for linha in linhas:
            if ocupado() + linha.escala > limite:
                nova()
            paginas[-1].linhas.append(linha)
    for pagina in paginas:  # sem linha vazia sobrando no fim da página
        while pagina.linhas and not pagina.linhas[-1].texto and not pagina.linhas[-1].brasao:
            pagina.linhas.pop()
    return paginas


def posicoes_das_palavras(linha: Linha, estilo: Estilo) -> list[tuple[float, str, bool]]:
    """(x em pontos a partir da margem, palavra, negrito) de cada palavra da linha."""
    recuo = len(linha.texto) - len(linha.texto.lstrip())
    palavras, inicios, inicio = [], [], recuo
    for palavra in linha.texto.split():
        inicio = linha.texto.index(palavra, inicio)
        palavras.append((palavra, linha.negrito or inicio < linha.prefixo_negrito))
        inicios.append(inicio)
        inicio += len(palavra)
    if not palavras:
        return []
    if linha.alinhamento == "esquerda":
        # respeita os espaços do texto (colunas como "MATRÍCULA Nº 1.234      FICHA 01")
        return [(estilo.medir(linha.texto[:i], linha.negrito, linha.escala), p, n)
                for i, (p, n) in zip(inicios, palavras, strict=True)]
    larguras = [estilo.medir(p, n, linha.escala) for p, n in palavras]
    espaco = estilo.medir(" ", escala=linha.escala)
    natural = sum(larguras) + espaco * (len(palavras) - 1)
    x = estilo.medir(" " * recuo, escala=linha.escala)
    if linha.alinhamento == "centro":
        x = (estilo.largura_texto_pt - natural) / 2
    elif len(palavras) > 1:  # justificado
        espaco += (estilo.largura_texto_pt - natural - x) / (len(palavras) - 1)
    resultado = []
    for (palavra, negrito), largura in zip(palavras, larguras, strict=True):
        resultado.append((x, palavra, negrito))
        x += largura + espaco
    return resultado


# ---------------------------------------------------------------- desenho


class _Desenhista:
    def __init__(self, estilo: Estilo, qualidade: Qualidade, rng: random.Random):
        self.e = estilo
        self.q = qualidade
        self.rng = rng
        self.escala = qualidade.dpi / 72  # pixels por ponto
        largura, altura = (round(v * self.escala) for v in estilo.tamanho_pt)
        self.imagem = Image.new("RGB", (largura, altura), (255, 255, 255))
        self.d = ImageDraw.Draw(self.imagem)

    def px(self, pt: float) -> float:
        return pt * self.escala

    def fonte(self, negrito: bool, escala: float = 1.0) -> ImageFont.FreeTypeFont:
        return _fonte(self.e.fonte, negrito, round(self.px(self.e.corpo_pt * escala)))

    def tinta(self) -> tuple[int, int, int]:
        """Máquina: cada letra sai um pouco mais clara ou escura. Laser: tom uniforme."""
        variacao = 40 if self.e.maquina else 8
        clarear = (self.q.desbotamento * 110
                   + self.rng.uniform(0, variacao) * (0.3 + self.q.desbotamento))
        return tuple(min(255, int(c + clarear)) for c in TINTA_PRETA)

    def palavra(self, x: float, y: float, texto: str, negrito: bool, escala: float) -> None:
        fonte = self.fonte(negrito, escala)
        if not self.e.maquina:
            self.d.text((x, y), texto, font=fonte, fill=self.tinta())
            return
        passo = self.px(self.e.corpo_pt * 0.6 * escala)
        tremor = 0.25 * self.escala
        for i, caractere in enumerate(texto):
            dx = self.rng.uniform(-tremor, tremor)
            dy = self.rng.uniform(-tremor, tremor)
            self.d.text((x + i * passo + dx, y + dy), caractere, font=fonte, fill=self.tinta())

    def rubrica(self, x: float, y: float, tamanho: float, cor=TINTA_AZUL) -> None:
        """Rabisco curvo que imita uma rubrica/assinatura à caneta."""
        pontos = []
        voltas = self.rng.randint(3, 6)
        fase = self.rng.uniform(0, math.pi)
        for k in range(120):
            t = k / 119
            px = x + t * tamanho
            py = y + math.sin(t * voltas * math.pi + fase) * tamanho * 0.18 * (1.2 - t)
            py += math.sin(t * 17 + fase) * tamanho * 0.04
            pontos.append((px, py))
        espessura = max(1, round(self.escala * 0.9))
        self.d.line(pontos, fill=cor, width=espessura, joint="curve")
        self.d.line([(x, y + tamanho * 0.22), (x + tamanho * 1.05, y + tamanho * 0.18)],
                    fill=cor, width=espessura)

    def brasao(self, cx: float, cy: float, raio: float, cor, imagem: Image.Image | None = None,
               opacidade: int = 255) -> None:
        """Emblema fictício: anéis, estrela de cinco pontas e raios (não é um brasão real)."""
        alvo = imagem or self.imagem
        camada = Image.new("RGBA", alvo.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(camada)
        tinta = (*cor, opacidade)
        largura = max(1, round(raio * 0.05))
        d.ellipse([cx - raio, cy - raio, cx + raio, cy + raio], outline=tinta, width=largura)
        d.ellipse([cx - raio * 0.8, cy - raio * 0.8, cx + raio * 0.8, cy + raio * 0.8],
                  outline=tinta, width=max(1, largura // 2))
        for k in range(24):  # raios
            angulo = 2 * math.pi * k / 24
            d.line([(cx + math.cos(angulo) * raio * 0.55, cy + math.sin(angulo) * raio * 0.55),
                    (cx + math.cos(angulo) * raio * 0.78, cy + math.sin(angulo) * raio * 0.78)],
                   fill=tinta, width=largura)
        estrela = []
        for k in range(10):
            angulo = -math.pi / 2 + math.pi * k / 5
            r = raio * (0.5 if k % 2 == 0 else 0.2)
            estrela.append((cx + math.cos(angulo) * r, cy + math.sin(angulo) * r))
        d.polygon(estrela, fill=tinta)
        alvo.paste(camada, (0, 0), camada)

    def carimbo(self, cx: float, cy: float, carimbo: Carimbo) -> None:
        """Carimbo semitransparente, levemente girado, sobre o que já estiver na página."""
        cor = self.rng.choice(TINTA_CARIMBO)
        lado = round(self.px(150))
        camada = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        d = ImageDraw.Draw(camada)
        fonte = _fonte("courier", True, round(self.px(7.5)))
        largura = max(1, round(self.px(1.4)))
        opaco = (*cor, 170)
        if carimbo.redondo:
            m = largura * 2
            d.ellipse([m, m, lado - m, lado - m], outline=opaco, width=largura)
            d.ellipse([lado * 0.14, lado * 0.14, lado * 0.86, lado * 0.86], outline=opaco,
                      width=max(1, largura // 2))
        else:
            d.rectangle([lado * 0.02, lado * 0.25, lado * 0.98, lado * 0.75], outline=opaco,
                        width=largura)
        altura_linha = self.px(9)
        topo = lado / 2 - altura_linha * len(carimbo.linhas) / 2
        for i, texto in enumerate(carimbo.linhas):
            d.text((lado / 2, topo + i * altura_linha), texto, font=fonte, fill=opaco, anchor="ma")
        camada = camada.rotate(self.rng.uniform(-25, 25), resample=Image.BICUBIC)
        self.imagem.paste(camada, (round(cx - lado / 2), round(cy - lado / 2)), camada)

    def carimbo_copia(self) -> None:
        """Carimbo "CÓPIA" (avisa que a certidão é cópia da original), em tamanho variado."""
        tamanho = self.px(self.rng.uniform(14, 30))
        fonte = _fonte("arial", True, round(tamanho))
        largura, altura = round(tamanho * 4.2), round(tamanho * 1.6)
        camada = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
        ImageDraw.Draw(camada).text((largura / 2, altura / 2), "CÓPIA", font=fonte,
                                    fill=(*TINTA_COPIA, 200), anchor="mm")
        camada = camada.rotate(self.rng.uniform(-6, 6), resample=Image.BICUBIC, expand=True)
        w, h = self.imagem.size
        x = self.rng.uniform(0.45, 0.85) * w - camada.width / 2
        y = self.rng.uniform(0.12, 0.88) * h - camada.height / 2
        self.imagem.paste(camada, (round(x), round(y)), camada)

    def selo(self, x: float, y: float, codigo: str) -> None:
        """Selo de fiscalização com código e um quadriculado que lembra um QR code."""
        lado = self.px(42)
        celula = lado / 21
        self.d.rectangle([x, y, x + lado, y + lado], outline=TINTA_PRETA,
                         width=max(1, round(self.escala)))
        gerador = random.Random(codigo)
        for i in range(21):
            for j in range(21):
                canto = (i < 7 and j < 7) or (i < 7 and j > 13) or (i > 13 and j < 7)
                if canto or gerador.random() < 0.45:
                    self.d.rectangle([x + i * celula, y + j * celula,
                                      x + (i + 1) * celula, y + (j + 1) * celula], fill=TINTA_PRETA)
        fonte = _fonte("arial", False, round(self.px(7)))
        self.d.text((x + lado + self.px(6), y + self.px(8)), "SELO DIGITAL DE FISCALIZAÇÃO",
                    font=fonte, fill=TINTA_PRETA)
        self.d.text((x + lado + self.px(6), y + self.px(20)), codigo, font=fonte, fill=TINTA_PRETA)

    # ------------------------------------------------ papel de segurança

    def fibras(self) -> None:
        w, h = self.imagem.size
        for _ in range(self.rng.randint(60, 140)):
            x, y = self.rng.uniform(0, w), self.rng.uniform(0, h)
            comprimento = self.px(self.rng.uniform(2, 7))
            angulo = self.rng.uniform(0, math.pi)
            curva = self.rng.uniform(-0.3, 0.3)
            pontos = [(x + math.cos(angulo + curva * t) * comprimento * t,
                       y + math.sin(angulo + curva * t) * comprimento * t)
                      for t in np.linspace(0, 1, 6)]
            self.d.line(pontos, fill=self.rng.choice(CORES_FIBRAS),
                        width=max(1, round(self.px(0.4))))

    def faixas_borda(self) -> None:
        """Faixas de segurança: escura à esquerda (com emblema), padrão verde à direita."""
        w, h = self.imagem.size
        esquerda = self.px(self.e.margem_pt * 0.55)
        for k in range(0, round(esquerda), max(2, round(self.px(0.8)))):
            pontos = [(k + math.sin(y / self.px(6) + k) * self.px(1.5), y)
                      for y in range(0, h, max(4, round(self.px(3))))]
            self.d.line(pontos, fill=COR_FAIXA_ESQUERDA, width=max(2, round(self.px(0.7))))
        self.brasao(esquerda / 2, self.px(40), esquerda * 0.42, (40, 40, 45))
        direita = self.px(self.e.margem_pt * 0.35)
        for k in range(0, round(direita), max(2, round(self.px(1.5)))):
            pontos = [(w - direita + k + math.sin(y / self.px(4) + k * 0.7) * self.px(2), y)
                      for y in range(0, h, max(4, round(self.px(3))))]
            self.d.line(pontos, fill=COR_FAIXA_DIREITA, width=1)

    def faixa_topo(self) -> None:
        w = self.imagem.size[0]
        x0, x1 = self.px(self.e.margem_pt * 0.4), w - self.px(self.e.margem_pt * 0.4)
        y0, y1 = self.px(8), self.px(self.e.margem_pt - 10)
        self.d.rectangle([x0, y0, x1, y1], fill=COR_FAIXA_ESQUERDA)
        raio = (y1 - y0) * 0.38
        for cx in (x0 + (y1 - y0) * 0.6, x1 - (y1 - y0) * 0.6):
            self.brasao(cx, (y0 + y1) / 2, raio, (235, 235, 235))

    def marca_dagua(self) -> None:
        w, h = self.imagem.size
        self.brasao(w / 2, h * 0.5, w * 0.17, COR_MARCA_DAGUA, opacidade=235)

    def riscos_diagonais(self, y_inicio: float) -> None:
        """Anula o espaço em branco depois do texto (impede acréscimos)."""
        x0 = self.px(self.e.x_texto_pt)
        x1 = x0 + self.px(self.e.largura_texto_pt)
        y1 = self.px(self.e.tamanho_pt[1] - self.e.margem_pt)
        if y1 - y_inicio < self.px(60):
            return
        y0 = max(y_inicio, y1 - self.px(220))  # grupo de riscos embaixo, à direita
        for k in range(self.rng.randint(3, 5)):
            deslocamento = self.px(6) * k
            self.d.line([(x0 + (x1 - x0) * 0.55 + deslocamento, y1 - deslocamento),
                         (x1, y0 + self.px(10) + deslocamento)],
                        fill=TINTA_PRETA, width=max(1, round(self.px(0.6))))


def renderizar(pagina: Pagina, qualidade: Qualidade, rng: random.Random,
               estilo: Estilo = ESTILO_PADRAO) -> Image.Image:
    """Desenha a página limpa (antes da degradação)."""
    des = _Desenhista(estilo, qualidade, rng)
    if estilo.papel_seguranca:
        des.marca_dagua()
        des.fibras()
    if estilo.faixas_borda and not pagina.verso:
        des.faixas_borda()
    if pagina.faixa_topo:
        des.faixa_topo()

    x0 = des.px(estilo.x_texto_pt)
    y = des.px(estilo.margem_pt)
    topos: list[float] = []
    for linha in pagina.linhas:
        topos.append(y)
        altura = des.px(estilo.entrelinha_pt * linha.escala)
        if linha.brasao:
            des.brasao(x0 + des.px(estilo.largura_texto_pt) / 2, y + altura / 2, altura * 0.45,
                       TINTA_PRETA)
        ultimo_x = x0
        for x, palavra, negrito in posicoes_das_palavras(linha, estilo):
            des.palavra(x0 + des.px(x), y, palavra, negrito, linha.escala)
            ultimo_x = x0 + des.px(x + estilo.medir(palavra, negrito, linha.escala))
        if linha.assinar:
            centro = x0 + des.px(estilo.largura_texto_pt) / 2
            des.rubrica(centro - des.px(55), y - altura * 0.2, des.px(110))
        if pagina.rubricas_apos and linha.texto_limpo.endswith(pagina.rubricas_apos):
            des.rubrica(ultimo_x + des.px(8), y + altura * 0.4, des.px(45))
        y += altura
    topos.append(y)

    espessura = max(1, round(des.escala * 0.8))
    for inicio, fim in pagina.molduras:
        des.d.rectangle([x0 - des.px(6), topos[inicio] - des.px(4),
                         x0 + des.px(estilo.largura_texto_pt) + des.px(6), topos[fim]],
                        outline=TINTA_PRETA, width=espessura)
    if pagina.rubrica_margem:
        x_margem = x0 + des.px(estilo.largura_texto_pt) + des.px(6)
        des.rubrica(x_margem, des.px(rng.uniform(250, 450)), des.px(28))

    rodape = y + des.px(10)
    if pagina.anular_espaco:
        des.riscos_diagonais(rodape)
    for i in range(pagina.assinaturas):
        des.rubrica(des.px(150 + 200 * (i % 2)), rodape + des.px(30 + 45 * (i // 2)),
                    des.px(110))
    for i, carimbo in enumerate(pagina.carimbos):
        des.carimbo(des.px(140 + 170 * i) + des.px(rng.uniform(-15, 15)),
                    rodape + des.px(40 + rng.uniform(-30, 10)), carimbo)
    if pagina.selo:
        des.selo(x0, des.px(estilo.tamanho_pt[1] - estilo.margem_pt - 50), pagina.selo)
    for _ in range(pagina.copias):
        des.carimbo_copia()
    return des.imagem


def transparencia(frente: Image.Image, intensidade: float = 0.07) -> Image.Image:
    """Verso em branco: o texto da frente aparece espelhado e bem fraco."""
    matriz = np.asarray(frente.transpose(Image.FLIP_LEFT_RIGHT), dtype=np.float32)
    return Image.fromarray((255 - (255 - matriz) * intensidade).astype(np.uint8))


# ---------------------------------------------------------------- degradação


def degradar(imagem: Image.Image, qualidade: Qualidade, rng: random.Random,
             estilo: Estilo = ESTILO_PADRAO) -> Image.Image:
    """Aplica os defeitos da digitalização (e do envelhecimento, nas qualidades piores)."""
    semente = rng.randint(0, 2**31)
    gerador = np.random.default_rng(semente)
    matriz = np.asarray(imagem, dtype=np.float32)
    altura, largura = matriz.shape[:2]

    # Cor do papel com manchas suaves (ruído de baixa frequência ampliado).
    tom = np.array(CORES_PAPEL[estilo.cor_papel], dtype=np.float32) - qualidade.desbotamento * 15
    manchas = gerador.normal(0, 1, (max(2, altura // 250), max(2, largura // 250)))
    manchas = np.asarray(Image.fromarray(((manchas + 3) * 40).clip(0, 255).astype(np.uint8))
                         .resize((largura, altura), Image.BICUBIC), dtype=np.float32)
    intensidade = 0.01 if qualidade.desbotamento == 0 else 0.04 * (1 + 2 * qualidade.desbotamento)
    papel = tom - (manchas[..., None] - 120) * intensidade
    tinta = 1 - matriz / 255  # 1 onde há tinta, 0 no branco
    matriz = papel * (1 - tinta) + matriz * tinta

    for _ in range(qualidade.sujeira):  # pontos de sujeira
        y, x = gerador.integers(0, altura), gerador.integers(0, largura)
        raio = int(gerador.integers(1, max(2, qualidade.dpi // 100) + 1))
        matriz[max(0, y - raio):y + raio, max(0, x - raio):x + raio] *= gerador.uniform(0.2, 0.7)

    imagem = Image.fromarray(matriz.clip(0, 255).astype(np.uint8))

    # Inclinação (o papel entrou torto no scanner); a borda descoberta fica cinza.
    angulo = rng.uniform(-qualidade.inclinacao_max, qualidade.inclinacao_max)
    imagem = imagem.rotate(angulo, resample=Image.BICUBIC, fillcolor=(200, 200, 200))
    if qualidade.desfoque:
        imagem = imagem.filter(ImageFilter.GaussianBlur(qualidade.desfoque))

    matriz = np.asarray(imagem, dtype=np.float32)
    matriz += gerador.normal(0, qualidade.ruido, matriz.shape[:2])[..., None]
    imagem = Image.fromarray(matriz.clip(0, 255).astype(np.uint8))
    if not qualidade.colorido:
        imagem = imagem.convert("L")
    return imagem


# ---------------------------------------------------------------- PDF


@dataclass
class DocumentoEscaneado:
    pdf: bytes
    texto_por_pagina: list[str]  # verdade para medir o OCR ("" nos versos em branco)
    inclinacao_max: float


def gerar_pdf_escaneado(paginas: list[Pagina], qualidade: str | Qualidade, semente: int,
                        estilo: Estilo = ESTILO_PADRAO) -> DocumentoEscaneado:
    q = QUALIDADES[qualidade] if isinstance(qualidade, str) else qualidade
    rng = random.Random(semente)
    documento = pymupdf.open()
    largura, altura = estilo.tamanho_pt
    frente_anterior: Image.Image | None = None
    for pagina in paginas:
        limpa = renderizar(pagina, q, rng, estilo)
        if pagina.verso and frente_anterior is not None:
            # o que foi desenhado no verso (ex.: "CÓPIA") por cima da transparência da frente
            limpa = Image.fromarray(np.minimum(np.asarray(limpa),
                                               np.asarray(transparencia(frente_anterior))))
        else:
            frente_anterior = limpa
        estilo_da_pagina = (replace(estilo, cor_papel=pagina.cor_papel) if pagina.cor_papel
                            else estilo)
        imagem = degradar(limpa, q, rng, estilo_da_pagina)
        buffer = io.BytesIO()
        imagem.save(buffer, format="JPEG", quality=q.jpeg, dpi=(q.dpi, q.dpi))
        folha = documento.new_page(width=largura, height=altura)
        folha.insert_image(folha.rect, stream=buffer.getvalue())
    documento.set_metadata({"producer": "Scanner fictício (Arquiteto Auditor - dados sintéticos)",
                            "title": "DOCUMENTO FICTÍCIO"})
    pdf = documento.tobytes(garbage=3, deflate=True)
    documento.close()
    return DocumentoEscaneado(pdf, [p.texto for p in paginas], q.inclinacao_max)
