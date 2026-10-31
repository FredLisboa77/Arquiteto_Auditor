"""Blocos de desenho arquitetônico (paredes, esquadrias, escada, mobiliário, figura humana...).

Todas as funções recebem coordenadas em milímetros de papel e `k` = milímetros de papel por
metro real (1000 / escala). Os blocos servem para dar às pranchas sintéticas a densidade de
desenho e de "números que não interessam" (cotas internas, níveis, áreas de ambientes,
dimensões de esquadrias) das pranchas reais, que confundem uma extração ingênua.
"""

from __future__ import annotations

import math

from dados_sinteticos.geradores.desenho import (
    PENA_FINA,
    PENA_GROSSA,
    PENA_MEDIA,
    Folha,
    Retangulo,
    formatar_numero,
)

CINZA_PAREDE = 0.25


# ---------------------------------------------------------------- planta: paredes e esquadrias


def parede(folha: Folha, r: Retangulo):
    """Parede cortada: retângulo cheio (pochê)."""
    folha.preenchido(r, CINZA_PAREDE)


def vao_branco(folha: Folha, r: Retangulo):
    folha.preenchido(r, 1.0)


def porta(folha: Folha, x, y, largura, espessura_parede, horizontal: bool, para_dentro: int,
          rotulo: str):
    """Porta de giro: vão na parede, folha e arco de abertura.

    horizontal: parede horizontal (vão ao longo de x). para_dentro: +1 abre para cima/direita,
    -1 para baixo/esquerda. (x, y) é o início do vão no eixo da parede.
    """
    meia = espessura_parede / 2
    if horizontal:
        vao_branco(folha, Retangulo(x, y - meia, largura, espessura_parede))
        folha.linha(x, y, x, y + para_dentro * largura, PENA_MEDIA)
        inicio = 0 if para_dentro > 0 else 270
        folha.arco(x, y, largura, inicio, 90)
        folha.texto(x + largura / 2, y + para_dentro * (largura * 0.35) - 1, rotulo, escala=0.6,
                    alinhamento="centro")
    else:
        vao_branco(folha, Retangulo(x - meia, y, espessura_parede, largura))
        folha.linha(x, y, x + para_dentro * largura, y, PENA_MEDIA)
        inicio = 0 if para_dentro > 0 else 90
        folha.arco(x, y, largura, inicio, 90)
        folha.texto(x + para_dentro * largura * 0.35, y + largura / 2, rotulo, escala=0.6,
                    alinhamento="centro")


def janela(folha: Folha, x, y, comprimento, espessura_parede, horizontal: bool, rotulo: str,
           lado_rotulo: int = -1):
    """Janela em planta: vão com três linhas (caixilho e vidro)."""
    meia = espessura_parede / 2
    if horizontal:
        vao_branco(folha, Retangulo(x, y - meia, comprimento, espessura_parede))
        for desloc in (-meia, 0, meia):
            folha.linha(x, y + desloc, x + comprimento, y + desloc, PENA_FINA)
        folha.texto(x + comprimento / 2, y + lado_rotulo * (meia + 3) - 1, rotulo, escala=0.6,
                    alinhamento="centro")
    else:
        vao_branco(folha, Retangulo(x - meia, y, espessura_parede, comprimento))
        for desloc in (-meia, 0, meia):
            folha.linha(x + desloc, y, x + desloc, y + comprimento, PENA_FINA)
        folha.texto(x + lado_rotulo * (meia + 4), y + comprimento / 2, rotulo, escala=0.6,
                    alinhamento="centro")


def pilar(folha: Folha, x, y, k):
    lado = 0.20 * k
    folha.preenchido(Retangulo(x - lado / 2, y - lado / 2, lado, lado), 0.0)


def escada(folha: Folha, r: Retangulo, k, sobe: bool):
    """Degraus de 28 cm, linha de percurso com seta e indicação SOBE/DESCE."""
    passo = 0.28 * k
    y = r.y + passo
    while y < r.topo - passo / 2:
        folha.linha(r.x, y, r.direita, y, PENA_FINA)
        y += passo
    centro = r.x + r.largura / 2
    folha.linha(centro, r.y + passo / 2, centro, r.topo - passo, PENA_FINA)
    folha.poligono([(centro - 1.2, r.topo - passo), (centro + 1.2, r.topo - passo),
                    (centro, r.topo - passo + 2.5)], cheio=True)
    folha.texto(centro, r.y + passo * 0.3, folha.rotulo("Sobe" if sobe else "Desce"),
                escala=0.55, alinhamento="centro")


def hachura_piso(folha: Folha, r: Retangulo, k, passo_m=0.40):
    """Paginação de piso cerâmico (áreas molhadas)."""
    passo = passo_m * k
    x = r.x + passo
    while x < r.direita:
        folha.linha(x, r.y, x, r.topo, 0.08)
        x += passo
    y = r.y + passo
    while y < r.topo:
        folha.linha(r.x, y, r.direita, y, 0.08)
        y += passo


def hachura_diagonal(folha: Folha, r: Retangulo, passo=2.0):
    """Hachura a 45° dentro do retângulo (passeio, terreno em corte)."""
    deslocamento = -r.altura
    while deslocamento < r.largura:
        x1, y1 = r.x + deslocamento, r.y
        x2, y2 = x1 + r.altura, r.topo
        if x1 < r.x:
            y1 += r.x - x1
            x1 = r.x
        if x2 > r.direita:
            y2 -= x2 - r.direita
            x2 = r.direita
        if y2 > y1:
            folha.linha(x1, y1, x2, y2, 0.08)
        deslocamento += passo


def grama(folha: Folha, r: Retangulo, passo=4.0):
    """Símbolo de gramado: pequenos tufos em "v" distribuídos em quincôncio."""
    linha = 0
    y = r.y + passo / 2
    while y < r.topo - 1:
        x = r.x + passo / 2 + (passo / 2 if linha % 2 else 0)
        while x < r.direita - 1:
            folha.linha(x - 0.6, y + 1.0, x, y, 0.08)
            folha.linha(x, y, x + 0.6, y + 1.0, 0.08)
            x += passo
        y += passo * 0.8
        linha += 1


# ---------------------------------------------------------------- planta: mobiliário e louças


def _caixa(folha: Folha, cx, cy, largura_m, profundidade_m, k, espessura=PENA_FINA):
    r = Retangulo(cx - largura_m * k / 2, cy - profundidade_m * k / 2, largura_m * k,
                  profundidade_m * k)
    folha.retangulo(r, espessura)
    return r


def carro(folha: Folha, cx, cy, k):
    r = _caixa(folha, cx, cy, 1.8, 4.3, k)
    folha.linha(r.x + 0.15 * k, r.y + 2.9 * k, r.direita - 0.15 * k, r.y + 2.9 * k, PENA_FINA)
    folha.linha(r.x + 0.15 * k, r.y + 1.2 * k, r.direita - 0.15 * k, r.y + 1.2 * k, PENA_FINA)


def sofa(folha: Folha, cx, cy, k):
    r = _caixa(folha, cx, cy, 2.1, 0.85, k)
    folha.linha(r.x, r.y + 0.65 * k, r.direita, r.y + 0.65 * k, PENA_FINA)


def mesa_jantar(folha: Folha, cx, cy, k):
    _caixa(folha, cx, cy, 1.6, 0.9, k)
    for dx in (-0.45, 0.45):
        for dy in (-0.7, 0.7):
            _caixa(folha, cx + dx * k, cy + dy * k, 0.4, 0.4, k)


def cama(folha: Folha, cx, cy, k, casal: bool):
    r = _caixa(folha, cx, cy, 1.6 if casal else 0.9, 2.0, k)
    folha.linha(r.x, r.topo - 0.45 * k, r.direita, r.topo - 0.45 * k, PENA_FINA)


def vaso(folha: Folha, cx, cy, k):
    _caixa(folha, cx, cy + 0.25 * k, 0.4, 0.18, k)
    folha.elipse(cx, cy - 0.05 * k, 0.18 * k, 0.24 * k)


def lavatorio(folha: Folha, cx, cy, k):
    _caixa(folha, cx, cy, 0.55, 0.42, k)
    folha.elipse(cx, cy, 0.18 * k, 0.13 * k)


def chuveiro(folha: Folha, cx, cy, k):
    r = _caixa(folha, cx, cy, 0.9, 0.9, k)
    folha.linha(r.x, r.y, r.direita, r.topo, PENA_FINA)
    folha.linha(r.x, r.topo, r.direita, r.y, PENA_FINA)


def bancada_cozinha(folha: Folha, cx, cy, k):
    r = _caixa(folha, cx, cy, 2.4, 0.6, k)
    folha.retangulo(Retangulo(r.x + 0.2 * k, r.y + 0.1 * k, 0.8 * k, 0.4 * k), PENA_FINA)
    for i in range(4):  # fogão de 4 bocas
        folha.circulo(r.direita - (0.25 + 0.3 * (i % 2)) * k, r.y + (0.18 + 0.25 * (i // 2)) * k,
                      0.08 * k)


def tanque(folha: Folha, cx, cy, k):
    _caixa(folha, cx, cy, 0.6, 0.55, k)
    folha.circulo(cx, cy, 0.1 * k)


MOBILIA = {
    "carro": carro, "sofa": sofa, "mesa": mesa_jantar, "cozinha": bancada_cozinha,
    "tanque": tanque,
    "cama_casal": lambda f, x, y, k: cama(f, x, y, k, casal=True),
    "cama_solteiro": lambda f, x, y, k: cama(f, x, y, k, casal=False),
}


def banheiro(folha: Folha, r: Retangulo, k, com_chuveiro: bool):
    vaso(folha, r.x + 0.35 * k, r.topo - 0.45 * k, k)
    lavatorio(folha, r.direita - 0.4 * k, r.topo - 0.35 * k, k)
    if com_chuveiro and r.altura > 1.4 * k:
        chuveiro(folha, r.direita - 0.5 * k, r.y + 0.5 * k, k)


# ---------------------------------------------------------------- vistas: corte e fachada


def pessoa(folha: Folha, x, y_solo, k):
    """Figura humana de 1,70 m (escala humana)."""
    def p(dx, dy):
        return (x + dx * k, y_solo + dy * k)

    folha.circulo(*p(0, 1.58), 0.11 * k, PENA_FINA)
    folha.poligono([p(-0.08, 1.46), p(-0.24, 1.40), p(-0.27, 0.85), p(-0.20, 0.85),
                    p(-0.17, 1.25), p(-0.15, 0.92), p(-0.13, 0.0), p(-0.03, 0.0), p(0.0, 0.80),
                    p(0.03, 0.0), p(0.13, 0.0), p(0.15, 0.92), p(0.17, 1.25), p(0.20, 0.85),
                    p(0.27, 0.85), p(0.24, 1.40), p(0.08, 1.46)], PENA_FINA)


def nivel(folha: Folha, x, y, valor_m: float):
    """Marca de nível: triângulo e cota de nível (ex.: +2,90)."""
    folha.poligono([(x - 1.5, y + 2.2), (x + 1.5, y + 2.2), (x, y)], PENA_FINA)
    sinal = "+" if valor_m >= 0 else "-"
    folha.texto(x + 2.5, y + 1.0, f"{sinal}{formatar_numero(abs(valor_m))}", escala=0.7)


def linha_de_terra(folha: Folha, x1, x2, y):
    folha.linha(x1, y, x2, y, PENA_GROSSA * 2)
    hachura_diagonal(folha, Retangulo(x1, y - 3.5, x2 - x1, 3.5), passo=2.5)


def esquadria_vista(folha: Folha, r: Retangulo, folhas: int = 2):
    """Janela em vista: marco, folhas e reflexo do vidro."""
    folha.retangulo(r, PENA_MEDIA)
    interno = Retangulo(r.x + 0.6, r.y + 0.6, r.largura - 1.2, r.altura - 1.2)
    folha.retangulo(interno, PENA_FINA)
    for i in range(1, folhas):
        x = r.x + r.largura * i / folhas
        folha.linha(x, r.y, x, r.topo, PENA_FINA)
    folha.linha(interno.x + 1, interno.y + interno.altura * 0.3, interno.x + interno.largura * 0.3,
                interno.topo - 1, 0.08)


def portao(folha: Folha, r: Retangulo, k):
    folha.retangulo(r, PENA_MEDIA)
    y = r.y + 0.15 * k
    while y < r.topo:
        folha.linha(r.x, y, r.direita, y, 0.08)
        y += 0.15 * k


def chamada(folha: Folha, x_ponto, y_ponto, x_texto, y_texto, texto: str):
    """Nota de material com linha de chamada."""
    folha.circulo(x_ponto, y_ponto, 0.5, cheio=True)
    folha.linha(x_ponto, y_ponto, x_texto, y_texto, PENA_FINA)
    folha.linha(x_texto, y_texto, x_texto + 3, y_texto, PENA_FINA)
    folha.texto(x_texto + 4, y_texto - 1, texto, escala=0.65)


def seta(folha: Folha, x1, y1, x2, y2):
    folha.linha(x1, y1, x2, y2, PENA_FINA)
    angulo = math.atan2(y2 - y1, x2 - x1)
    pontas = [(x2 - 2.5 * math.cos(angulo + d), y2 - 2.5 * math.sin(angulo + d))
              for d in (0.4, -0.4)]
    folha.poligono([(x2, y2), *pontas], PENA_FINA, cheio=True)
