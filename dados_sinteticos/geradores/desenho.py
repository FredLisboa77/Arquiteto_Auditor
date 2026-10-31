"""Primitivas de desenho técnico em milímetros sobre o canvas do ReportLab."""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from dados_sinteticos.geradores.especificacao import Projeto

MM = 72 / 25.4
TAMANHOS_MM = {"A1": (841.0, 594.0), "A2": (594.0, 420.0), "A3": (420.0, 297.0)}
TAMANHO_FONTE = {"A1": 10.0, "A2": 8.5, "A3": 7.0}
# Hierarquia de penas (mm): elementos cortados grossos, vistas médias, hachuras finas.
PENA_GROSSA, PENA_MEDIA, PENA_FINA = 0.5, 0.3, 0.13

pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))
pdfmetrics.registerFont(TTFont("VeraBd", "VeraBd.ttf"))


def formatar_numero(valor: float, decimal_ponto: bool = False, casas: int = 2) -> str:
    if decimal_ponto:
        return f"{valor:.{casas}f}"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


@dataclass
class Retangulo:
    x: float
    y: float
    largura: float
    altura: float

    @property
    def topo(self) -> float:
        return self.y + self.altura

    @property
    def direita(self) -> float:
        return self.x + self.largura


class Folha:
    """Canvas com coordenadas em milímetros e utilitários de desenho técnico."""

    def __init__(self, c: canvas.Canvas, projeto: Projeto):
        self.c = c
        self.p = projeto
        self.v = projeto.variacao
        self.fonte = TAMANHO_FONTE[self.v.formato]
        self.largura_mm, self.altura_mm = TAMANHOS_MM[self.v.formato]

    # ------------------------------------------------ primitivas

    def rotulo(self, texto: str) -> str:
        return texto.upper() if self.v.caixa_alta else texto

    def num(self, valor: float) -> str:
        return formatar_numero(valor, self.v.decimal_ponto)

    def linha(self, x1, y1, x2, y2, espessura=0.25):
        self.c.setLineWidth(espessura * MM)
        self.c.line(x1 * MM, y1 * MM, x2 * MM, y2 * MM)

    def retangulo(self, r: Retangulo, espessura=0.25, tracejado=False):
        self.c.setLineWidth(espessura * MM)
        self.c.setDash(2 * MM, 1 * MM) if tracejado else self.c.setDash()
        self.c.rect(r.x * MM, r.y * MM, r.largura * MM, r.altura * MM)
        self.c.setDash()

    def texto(self, x, y, s, escala=1.0, negrito=False, alinhamento="esquerda", angulo=0):
        self.c.saveState()
        self.c.setFont("VeraBd" if negrito else "Vera", self.fonte * escala)
        self.c.translate(x * MM, y * MM)
        if angulo:
            self.c.rotate(angulo)
        desenhar = {"esquerda": self.c.drawString, "centro": self.c.drawCentredString,
                    "direita": self.c.drawRightString}[alinhamento]
        desenhar(0, 0, s)
        self.c.restoreState()

    def altura_texto(self, escala=1.0) -> float:
        return self.fonte * escala / MM

    def preenchido(self, r: Retangulo, cinza=0.35, contorno=False):
        """Retângulo cheio (ex.: parede ou laje cortada). cinza=1 é branco."""
        self.c.setFillGray(cinza)
        self.c.setLineWidth(PENA_FINA * MM)
        self.c.rect(r.x * MM, r.y * MM, r.largura * MM, r.altura * MM, fill=1,
                    stroke=1 if contorno else 0)
        self.c.setFillGray(0)

    def circulo(self, x, y, raio, espessura=PENA_FINA, cheio=False):
        self.c.setLineWidth(espessura * MM)
        self.c.circle(x * MM, y * MM, raio * MM, fill=1 if cheio else 0)

    def elipse(self, x, y, raio_x, raio_y, espessura=PENA_FINA):
        self.c.setLineWidth(espessura * MM)
        self.c.ellipse((x - raio_x) * MM, (y - raio_y) * MM, (x + raio_x) * MM,
                       (y + raio_y) * MM)

    def arco(self, cx, cy, raio, inicio, extensao, espessura=PENA_FINA):
        self.c.setLineWidth(espessura * MM)
        self.c.arc((cx - raio) * MM, (cy - raio) * MM, (cx + raio) * MM, (cy + raio) * MM,
                   inicio, extensao)

    def tracejada(self, x1, y1, x2, y2, espessura=PENA_FINA):
        self.c.setDash(1.5 * MM, 1 * MM)
        self.linha(x1, y1, x2, y2, espessura)
        self.c.setDash()

    def poligono(self, pontos, espessura=PENA_FINA, fechado=True, cheio=False):
        caminho = self.c.beginPath()
        caminho.moveTo(pontos[0][0] * MM, pontos[0][1] * MM)
        for x, y in pontos[1:]:
            caminho.lineTo(x * MM, y * MM)
        if fechado:
            caminho.close()
        self.c.setLineWidth(espessura * MM)
        self.c.drawPath(caminho, fill=1 if cheio else 0, stroke=1)

    # ------------------------------------------------ cota (linha de dimensão)

    def cota(self, x1, y1, x2, y2, valor: float, rotulo: str, elemento: str | None):
        """Linha de cota com traços oblíquos nas pontas e o texto acima.

        Se o elemento estiver em `cotas_omitidas`, desenha só a linha (dimensão "gráfica").
        """
        self.linha(x1, y1, x2, y2, PENA_FINA)
        for x, y in ((x1, y1), (x2, y2)):
            self.linha(x - 1.2, y - 1.2, x + 1.2, y + 1.2, PENA_MEDIA)
        if elemento in self.p.apresentacao.cotas_omitidas:
            return
        texto = self.num(valor)
        if self.v.cotas_rotuladas and rotulo:
            texto = f"{self.rotulo(rotulo)} {texto}"
        meio_x, meio_y = (x1 + x2) / 2, (y1 + y2) / 2
        if abs(x2 - x1) >= abs(y2 - y1):
            self.texto(meio_x, meio_y + 1.0, texto, alinhamento="centro")
        else:
            self.texto(meio_x - 1.0, meio_y, texto, alinhamento="centro", angulo=90)


