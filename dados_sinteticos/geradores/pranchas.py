"""Desenha as pranchas sintéticas em PDF vetorial (texto selecionável, como a saída do AutoCAD).

Folhas:  01 situação + localização + quadro de áreas
         02 plantas baixas (térreo e superior)
         03 corte e fachada (altura total e muro)

Todas as folhas trazem a marca "DOCUMENTO FICTÍCIO" e os metadados identificam a base sintética.
A assinatura digital é aplicada depois, por assinatura.py.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfgen import canvas

from dados_sinteticos.geradores import blocos
from dados_sinteticos.geradores.desenho import (  # noqa: F401 (reexportados para os testes)
    MM,
    PENA_FINA,
    PENA_GROSSA,
    PENA_MEDIA,
    TAMANHOS_MM,
    Folha,
    Retangulo,
    formatar_numero,
)
from dados_sinteticos.geradores.especificacao import Projeto

ESCALAS = (50, 75, 100, 125, 150, 200, 250, 300, 500)
DATA_EMISSAO = "15/09/2026"
# Largura do carimbo nos estilos 0 e 3 (proporcional ao formato da folha)
LARGURA_CARIMBO = {"A1": 175.0, "A2": 160.0, "A3": 125.0}
MARCA_FICTICIO = (
    "DOCUMENTO FICTÍCIO — BASE SINTÉTICA DO ARQUITETO AUDITOR — NÃO CORRESPONDE A IMÓVEL REAL"
)


# ---------------------------------------------------------------- escala


def escolher_escala(largura_m: float, altura_m: float, area: Retangulo, folga_mm=30,
                    minima: int = 50) -> int:
    """Menor denominador (desenho maior) que cabe na área, a partir da escala mínima."""
    for escala in (e for e in ESCALAS if e >= minima):
        if (largura_m * 1000 / escala + folga_mm <= area.largura
                and altura_m * 1000 / escala + folga_mm <= area.altura):
            return escala
    return ESCALAS[-1]


# ---------------------------------------------------------------- carimbos


@dataclass
class CampoCarimbo:
    rotulo: str
    valor: str


def campos_carimbo(folha: Folha, indice: int, titulo_folha: str):
    p, ident = folha.p, folha.p.identificacao
    alternativo = folha.v.estilo_carimbo == 3
    proprietario = ident.proprietario if p.apresentacao.mostrar_proprietario else ""
    if alternativo and proprietario:
        proprietario = f"{proprietario} — CPF {ident.cpf_proprietario}"
    rotulos = (
        ("Escritório", "Obra", "Local", "Condomínio", "Lote / Quadra", "Município", "Nº Mat.",
         "Interessado", "Resp. técnico", "Reg. prof.", "RRT nº", "Conteúdo", "Folha", "Rev.",
         "Escala", "Data")
        if alternativo else
        ("Escritório", "Projeto", "Endereço", "Condomínio", "Lote / Quadra", "Município",
         "Matrícula", "Proprietário", "Autor do projeto", "Registro", "RRT", "Conteúdo", "Prancha",
         "Revisão", "Escala", "Data")
    )
    valores = (
        ident.escritorio, ident.titulo, ident.endereco, ident.condominio,
        f"{ident.lote} / {ident.quadra}",
        ident.municipio, f"{p.matricula_prancha} — {ident.cartorio}", proprietario,
        ident.autor, ident.registro_autor, ident.rrt, titulo_folha,
        f"{indice + 1:02d}/{p.numero_folhas:02d}", p.revisao_da_folha(indice),
        folha.rotulo("Indicada"),
        DATA_EMISSAO,
    )
    return [CampoCarimbo(folha.rotulo(r), v) for r, v in zip(rotulos, valores, strict=True)]


def _carimbo_tabela(folha: Folha, r: Retangulo, campos, rotulo_acima: bool):
    """Uma coluna de campos; rótulo à esquerda (estilos 0 e 3) ou acima do valor (estilo 1)."""
    folha.retangulo(r, 0.5)
    altura_linha = r.altura / (len(campos) + 2)
    y = r.topo
    for campo in campos:
        y -= altura_linha
        folha.linha(r.x, y, r.direita, y, 0.18)
        if rotulo_acima:
            folha.texto(r.x + 1.5, y + altura_linha - folha.altura_texto(0.7) - 0.8,
                        campo.rotulo, escala=0.7)
            folha.texto(r.x + 1.5, y + 1.2, campo.valor, escala=0.95, negrito=True)
        else:
            folha.texto(r.x + 1.5, y + 1.2, campo.rotulo + ":", escala=0.8)
            folha.texto(r.x + r.largura * 0.3, y + 1.2, campo.valor, escala=0.9)
    # Espaço das assinaturas (visual)
    y_assinatura = r.y + altura_linha * 0.6
    for posicao, texto in ((0.05, "Autor do projeto"), (0.55, "Proprietário")):
        x = r.x + r.largura * posicao
        folha.linha(x, y_assinatura + 3, x + r.largura * 0.4, y_assinatura + 3, 0.18)
        folha.texto(x, y_assinatura, folha.rotulo(texto), escala=0.7)


def _carimbo_faixa(folha: Folha, r: Retangulo, campos):
    """Faixa horizontal na base da folha, com campos em colunas (estilo 2)."""
    folha.retangulo(r, 0.5)
    colunas = 5
    linhas = -(-len(campos) // colunas)
    largura_coluna = r.largura / colunas
    altura_linha = r.altura / linhas
    for i, campo in enumerate(campos):
        coluna, linha = i % colunas, i // colunas
        x = r.x + coluna * largura_coluna
        y = r.topo - (linha + 1) * altura_linha
        folha.retangulo(Retangulo(x, y, largura_coluna, altura_linha), 0.18)
        folha.texto(x + 1.5, y + altura_linha - folha.altura_texto(0.7) - 1, campo.rotulo,
                    escala=0.7)
        folha.texto(x + 1.5, y + 1.5, campo.valor, escala=0.85, negrito=True)


def _tabela_revisoes(folha: Folha, r: Retangulo, indice: int):
    """Quadro de revisões acima do carimbo (estilo 3)."""
    revisao_folha = folha.p.revisao_da_folha(indice)
    linhas = [("R00", DATA_EMISSAO, folha.rotulo("Emissão inicial"))]
    if revisao_folha != "R00":
        linhas.append((revisao_folha, DATA_EMISSAO, folha.rotulo("Revisão geral")))
    altura = folha.altura_texto() + 2.5
    y = r.topo + 2
    for codigo, data, descricao in reversed(linhas):
        folha.retangulo(Retangulo(r.x, y, r.largura, altura), 0.18)
        folha.texto(r.x + 1.5, y + 1.2, codigo, escala=0.85)
        folha.texto(r.x + 15, y + 1.2, data, escala=0.85)
        folha.texto(r.x + 40, y + 1.2, descricao, escala=0.85)
        y += altura
    return y


def desenhar_carimbo(folha: Folha, indice: int, titulo_folha: str):
    """Desenha o carimbo e devolve a área livre da folha para o desenho."""
    margem_esq, margem = 25.0, 10.0
    interna = Retangulo(margem_esq, margem, folha.largura_mm - margem_esq - margem,
                        folha.altura_mm - 2 * margem)
    folha.retangulo(interna, 0.6)
    campos = campos_carimbo(folha, indice, titulo_folha)
    estilo = folha.v.estilo_carimbo

    if estilo in (0, 3):
        largura = LARGURA_CARIMBO[folha.v.formato]
        r = Retangulo(interna.direita - largura, interna.y, largura,
                      min(110.0, interna.altura * 0.36))
        _carimbo_tabela(folha, r, campos, rotulo_acima=False)
        topo = _tabela_revisoes(folha, r, indice) if estilo == 3 else r.topo
        return Retangulo(interna.x, interna.y, interna.largura, interna.altura), Retangulo(
            r.x, topo, r.largura, interna.topo - topo)
    if estilo == 1:
        r = Retangulo(interna.direita - 90, interna.y, 90, interna.altura)
        _carimbo_tabela(folha, r, campos, rotulo_acima=True)
        livre = Retangulo(interna.x, interna.y, interna.largura - 90, interna.altura)
        return livre, None
    r = Retangulo(interna.x, interna.y, interna.largura, 45.0)
    _carimbo_faixa(folha, r, campos)
    livre = Retangulo(interna.x, r.topo, interna.largura, interna.altura - 45.0)
    return livre, None


def regioes(folha: Folha, indice: int, titulo_folha: str):
    """(área do desenho principal, coluna lateral para quadro e localização)."""
    livre, coluna = desenhar_carimbo(folha, indice, titulo_folha)
    if coluna is not None:  # estilos 0 e 3: coluna acima do carimbo
        principal = Retangulo(livre.x, livre.y, livre.largura - coluna.largura - 5, livre.altura)
        return principal, coluna
    largura_coluna = max(115.0, livre.largura * 0.38)
    principal = Retangulo(livre.x, livre.y, livre.largura - largura_coluna - 5, livre.altura)
    coluna = Retangulo(principal.direita + 5, livre.y, largura_coluna, livre.altura)
    return principal, coluna


# ---------------------------------------------------------------- quadro de áreas


def linhas_quadro(folha: Folha):
    p, n = folha.p, formatar_numero
    alternativo = folha.v.estilo_quadro == 3
    rotulos = (
        ("Área do lote", "Área coberta térreo", "Área 1º pavimento", "Área total construída",
         "Projeção", "Área permeável", "Índice de ocupação", "Índice de aproveitamento",
         "Índice de permeabilidade")
        if alternativo else
        ("Área do terreno", "Área construída térreo", "Área construída pav. superior",
         "Área construída total", "Área de projeção", "Área permeável", "Taxa de ocupação",
         "Coeficiente de aproveitamento", "Taxa de permeabilidade")
    )
    pav = p.edificacao.areas_pavimentos
    valores = (
        (n(p.area_terreno_prancha), "m²"), (n(pav[0]), "m²"), (n(pav[1]), "m²"),
        (n(p.area_total_prancha), "m²"), (n(p.edificacao.projecao), "m²"),
        (n(p.edificacao.area_permeavel), "m²"), (n(p.to_prancha), "%"),
        (n(p.ca_prancha), ""), (n(p.tp_prancha), "%"),
    )
    return [(folha.rotulo(r), v, u) for r, (v, u) in zip(rotulos, valores, strict=True)]


def desenhar_quadro(folha: Folha, x: float, topo: float, largura: float) -> float:
    """Desenha o quadro de áreas no estilo da variação; devolve o y da base."""
    linhas = linhas_quadro(folha)
    altura = folha.altura_texto() + 3
    estilo = folha.v.estilo_quadro
    folha.texto(x, topo - altura + 1.5, folha.rotulo("Quadro de áreas"), negrito=True)
    y = topo - altura

    if estilo == 0:  # tabela com linhas
        folha.retangulo(Retangulo(x, y - altura, largura, altura))
        folha.texto(x + 1.5, y - altura + 1.5, folha.rotulo("Descrição"), negrito=True)
        folha.texto(x + largura - 1.5, y - altura + 1.5, folha.rotulo("Área / índice"),
                    negrito=True, alinhamento="direita")
        y -= altura
        for rotulo, valor, unidade in linhas:
            folha.retangulo(Retangulo(x, y - altura, largura, altura), 0.18)
            folha.linha(x + largura * 0.68, y - altura, x + largura * 0.68, y, 0.18)
            folha.texto(x + 1.5, y - altura + 1.5, rotulo, escala=0.9)
            folha.texto(x + largura - 1.5, y - altura + 1.5, f"{valor} {unidade}".strip(),
                        escala=0.9, alinhamento="direita")
            y -= altura
        return y

    if estilo == 1:  # texto solto com pontilhado
        for rotulo, valor, unidade in linhas:
            y -= altura
            folha.texto(x, y, f"{rotulo} {'.' * 18} {valor} {unidade}".strip(), escala=0.9)
        return y

    if estilo == 2:  # colunas com unidade no cabeçalho
        areas, indices = linhas[:6], linhas[6:]
        largura_coluna = largura / 3
        y -= altura
        folha.texto(x, y, folha.rotulo("Áreas (m²)"), escala=0.85, negrito=True)
        for i, (rotulo, valor, _) in enumerate(areas):
            coluna, linha = i % 3, i // 3
            cx = x + coluna * largura_coluna
            cy = y - (linha + 1) * 2 * altura
            folha.retangulo(Retangulo(cx, cy, largura_coluna, 2 * altura), 0.18)
            folha.texto(cx + 1, cy + altura + 0.8, rotulo, escala=0.65)
            folha.texto(cx + 1, cy + 1.2, valor, escala=0.95, negrito=True)
        y -= 4 * altura + altura
        siglas = ("T.O.", "C.A.", "T.P.")
        texto = "   ".join(f"{s} = {v}{u}" for s, (_, v, u) in zip(siglas, indices, strict=True))
        folha.texto(x, y, texto, escala=0.9)
        return y

    # estilo 3: valor primeiro, rótulo depois
    for rotulo, valor, unidade in linhas:
        y -= altura
        folha.texto(x + 28, y, f"{valor} {unidade}".strip(), escala=0.9, alinhamento="direita")
        folha.texto(x + 31, y, f"— {rotulo}", escala=0.9)
    return y


# ---------------------------------------------------------------- folha 01: situação


def desenhar_norte(folha: Folha, x: float, y: float):
    if not folha.p.apresentacao.mostrar_norte:
        return
    raio = 7.0
    if folha.v.estilo_norte == "rosa":
        desenhar_rosa_dos_ventos(folha, x, y, raio)
        return
    folha.c.setLineWidth(0.25 * MM)
    folha.c.circle(x * MM, y * MM, raio * MM)
    caminho = folha.c.beginPath()
    caminho.moveTo(x * MM, (y + raio) * MM)
    caminho.lineTo((x - 2.5) * MM, (y - raio * 0.6) * MM)
    caminho.lineTo(x * MM, (y - raio * 0.2) * MM)
    caminho.close()
    folha.c.drawPath(caminho, fill=1, stroke=1)
    folha.texto(x, y + raio + 1.5, "N", escala=1.3, negrito=True, alinhamento="centro")


def desenhar_rosa_dos_ventos(folha: Folha, x: float, y: float, raio: float):
    """Rosa dos ventos de quatro pontas, com N, S, L e O."""
    folha.circulo(x, y, raio * 0.55, PENA_FINA)
    interno = raio * 0.18
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        ponta = (x + dx * raio, y + dy * raio)
        lateral_a = (x + dy * interno, y - dx * interno)
        lateral_b = (x - dy * interno, y + dx * interno)
        folha.poligono([ponta, lateral_a, (x, y)], PENA_FINA, cheio=(dx, dy) == (0, 1))
        folha.poligono([ponta, lateral_b, (x, y)], PENA_FINA)
    for letra, dx, dy in (("N", 0, 1), ("S", 0, -1), ("L", 1, 0), ("O", -1, 0)):
        folha.texto(x + dx * (raio + 3), y + dy * (raio + 3) - 1.2, letra,
                    escala=1.2 if letra == "N" else 0.8, negrito=letra == "N",
                    alinhamento="centro")


def desenhar_localizacao(folha: Folha, r: Retangulo):
    """Croqui da quadra com o lote destacado (sem escala)."""
    ident = folha.p.identificacao
    folha.texto(r.x, r.topo - folha.altura_texto(), folha.rotulo("Planta de localização"),
                negrito=True)
    folha.texto(r.x, r.topo - 2 * folha.altura_texto() - 1, folha.rotulo("Sem escala"),
                escala=0.75)
    largura_lote, altura_lote = min(14.0, r.largura / 5), 18.0
    base_y = r.topo - 2 * folha.altura_texto() - 6 - 2 * altura_lote
    for linha in range(2):
        for coluna in range(4):
            lote = Retangulo(r.x + coluna * largura_lote, base_y + linha * altura_lote,
                             largura_lote, altura_lote)
            folha.retangulo(lote, 0.5 if (linha, coluna) == (0, 1) else 0.18)
    folha.texto(r.x + 1.5 * largura_lote, base_y + altura_lote / 2,
                f"{folha.rotulo('Lote')} {ident.lote}", escala=0.75, alinhamento="centro")
    folha.texto(r.x, base_y - folha.altura_texto() - 1,
                f"{folha.rotulo('Quadra')} {ident.quadra} — {ident.condominio}", escala=0.8)


def desenhar_vizinhos(folha: Folha, lote: Retangulo, k: float):
    """Lotes vizinhos tracejados, com numeração (números que não são medidas)."""
    try:
        numero = int(folha.p.identificacao.lote)
    except ValueError:
        return
    largura = min(4.0 * k, 25.0)
    for x, n in ((lote.x - largura, numero - 1), (lote.direita, numero + 1)):
        if n < 1:
            continue
        vizinho = Retangulo(x, lote.y, largura, lote.altura)
        folha.retangulo(vizinho, PENA_FINA, tracejado=True)
        folha.texto(x + largura / 2, lote.y + lote.altura * 0.75,
                    f"{folha.rotulo('Lote')} {n}", escala=0.7, alinhamento="centro")


def desenhar_cobertura(folha: Folha, predio: Retangulo, k: float):
    """Planta de cobertura: beiral, cumeeira, caimentos, reservatório."""
    beiral = 0.6 * k
    contorno = Retangulo(predio.x - beiral, predio.y - beiral, predio.largura + 2 * beiral,
                         predio.altura + 2 * beiral)
    folha.retangulo(contorno, PENA_FINA, tracejado=True)
    meio_y = predio.y + predio.altura / 2
    folha.linha(contorno.x, meio_y, contorno.direita, meio_y, PENA_MEDIA)
    x_seta = predio.x + predio.largura * 0.75
    blocos.seta(folha, x_seta, meio_y - 2, x_seta, predio.y + predio.altura * 0.12)
    blocos.seta(folha, x_seta, meio_y + 2, x_seta, predio.topo - predio.altura * 0.12)
    for y in (predio.y + predio.altura * 0.25, predio.topo - predio.altura * 0.25):
        folha.texto(x_seta + 1.5, y, "i=30%", escala=0.65)
    lado = 1.2 * k
    caixa = Retangulo(predio.x + predio.largura * 0.15, meio_y + 2, lado, lado)
    folha.retangulo(caixa, PENA_MEDIA)
    folha.linha(caixa.x, caixa.y, caixa.direita, caixa.topo, PENA_FINA)
    folha.linha(caixa.x, caixa.topo, caixa.direita, caixa.y, PENA_FINA)
    folha.texto(caixa.x, caixa.topo + 1.5, folha.rotulo("Cx. d'água 1000 L"), escala=0.6)
    folha.texto(predio.x + predio.largura / 2, meio_y - 4,
                folha.rotulo("Projeção da edificação"), escala=0.7, alinhamento="centro")
    folha.texto(predio.x + predio.largura / 2, meio_y - 4 - folha.altura_texto(0.7) - 1,
                folha.rotulo("Cobertura em telha cerâmica"), escala=0.6, alinhamento="centro")
    folha.texto(contorno.direita + 1, contorno.topo - 3,
                f"{folha.rotulo('Beiral')} {folha.num(0.6)}", escala=0.6)


def desenhar_passeio(folha: Folha, lote: Retangulo, k: float) -> float:
    """Passeio, meio-fio, rebaixo e acessos. Devolve o y do meio-fio."""
    e = folha.p.edificacao
    passeio = Retangulo(lote.x - 12, lote.y - 2.0 * k, lote.largura + 24, 2.0 * k)
    blocos.hachura_diagonal(folha, passeio, passo=3.0)
    folha.linha(passeio.x, passeio.y, passeio.direita, passeio.y, PENA_GROSSA)
    folha.texto(passeio.direita + 2, passeio.y + passeio.altura / 2 - 1,
                folha.rotulo("Passeio"), escala=0.65)
    folha.texto(passeio.direita + 2, passeio.y - 1, folha.rotulo("Meio-fio"), escala=0.65)
    folha.texto(passeio.x + 3, passeio.y + 1.5, "i=2%", escala=0.6)
    folha.cota(passeio.x - 4, passeio.y, passeio.x - 4, lote.y, 2.0, "", None)
    x_garagem = lote.x + e.recuo_lateral_e * k
    largura_garagem = e.largura * 0.45 * k
    folha.tracejada(x_garagem, lote.y, x_garagem - 0.5 * k, passeio.y)
    folha.tracejada(x_garagem + largura_garagem, lote.y,
                    x_garagem + largura_garagem + 0.5 * k, passeio.y)
    acessos = ((x_garagem + largura_garagem / 2, "Acesso veículos"),
               (x_garagem + e.largura * 0.75 * k, "Acesso pedestres"))
    for x, texto in acessos:
        blocos.seta(folha, x, passeio.y - 7, x, lote.y + 3)
        folha.texto(x, passeio.y - 10, folha.rotulo(texto), escala=0.6, alinhamento="centro")
    return passeio.y


def desenhar_area_permeavel(folha: Folha, lote: Retangulo, predio: Retangulo, k: float):
    """Gramado no maior dos quintais (frente ou fundos), com a área do quadro de áreas."""
    beiral = 0.6 * k
    fundos = Retangulo(lote.x + 0.5 * k, predio.topo + beiral + 0.5 * k, lote.largura - k,
                       lote.topo - predio.topo - beiral - k)
    frente = Retangulo(predio.x + predio.largura * 0.5, lote.y + 0.5 * k,
                       lote.direita - predio.x - predio.largura * 0.5 - 0.5 * k,
                       predio.y - beiral - lote.y - k)
    area = max((fundos, frente), key=lambda r: r.largura * r.altura)
    if area.altura < 4 or area.largura < 10:
        return
    blocos.grama(folha, area)
    centro = area.x + area.largura / 2
    folha.texto(centro, area.y + area.altura / 2 + 1, folha.rotulo("Área permeável (grama)"),
                escala=0.65, alinhamento="centro")
    folha.texto(centro, area.y + area.altura / 2 - folha.altura_texto(0.65),
                f"A = {formatar_numero(folha.p.edificacao.area_permeavel)} m²", escala=0.65,
                alinhamento="centro")


def folha_situacao(folha: Folha, indice: int):
    p = folha.p
    t, e = p.terreno, p.edificacao
    principal, coluna = regioes(folha, indice, folha.rotulo("Situação e localização"))
    folha.texto(principal.x + 2, principal.topo - 4, MARCA_FICTICIO, escala=0.6)

    escala = escolher_escala(t.testada + 8, t.profundidade + 2.6, principal, folga_mm=50,
                             minima=100)
    k = 1000 / escala  # mm de papel por metro
    lote = Retangulo(principal.x + (principal.largura - t.testada * k) / 2,
                     principal.y + 32 + 2.0 * k, t.testada * k, t.profundidade * k)
    desenhar_vizinhos(folha, lote, k)
    folha.retangulo(lote, PENA_MEDIA)
    predio = Retangulo(lote.x + e.recuo_lateral_e * k, lote.y + e.recuo_frontal * k,
                       e.largura * k, e.profundidade * k)
    folha.retangulo(predio, PENA_GROSSA)
    desenhar_cobertura(folha, predio, k)
    meio_fio = desenhar_passeio(folha, lote, k)

    rua = p.identificacao.endereco.split(",")[0]
    folha.texto(lote.x + lote.largura / 2, meio_fio - 17, rua.upper(), alinhamento="centro")
    folha.texto(principal.x + 2, principal.y + 4,
                f"{folha.rotulo('Planta de situação')} — {folha.rotulo('Escala')} 1:{escala}",
                negrito=True)

    # Cotas do lote e dos recuos (as que o software precisa encontrar)
    folha.cota(lote.x, lote.y - 4, lote.direita, lote.y - 4, t.testada, "Testada", "testada")
    folha.cota(lote.x - 8, lote.y, lote.x - 8, lote.topo, t.profundidade, "Profundidade",
               "profundidade_lote")
    centro_x = predio.x + predio.largura * 0.4
    folha.cota(centro_x, lote.y, centro_x, predio.y, e.recuo_frontal, "Recuo frontal",
               "recuo_frontal")
    folha.cota(centro_x, predio.topo, centro_x, lote.topo, p.recuo_fundos, "Recuo de fundos",
               "recuo_fundos")
    centro_y = predio.y + predio.altura * 0.3
    folha.cota(lote.x, centro_y, predio.x, centro_y, e.recuo_lateral_e, "Lateral esq.",
               "recuo_lateral_e")
    folha.cota(predio.direita, centro_y, lote.direita, centro_y, p.recuo_lateral_d,
               "Lateral dir.", "recuo_lateral_d")

    # Cotas encadeadas (parciais e totais) — repetem os recuos; respeitam as omissões
    x_cadeia = lote.direita + 10
    for inicio, fim, valor, elemento in (
            (lote.y, predio.y, e.recuo_frontal, "recuo_frontal"),
            (predio.y, predio.topo, e.profundidade, None),
            (predio.topo, lote.topo, p.recuo_fundos, "recuo_fundos")):
        folha.cota(x_cadeia, inicio, x_cadeia, fim, valor, "", elemento)
    folha.cota(x_cadeia + 7, lote.y, x_cadeia + 7, lote.topo, t.profundidade, "",
               "profundidade_lote")
    y_cadeia = lote.topo + 6
    for inicio, fim, valor, elemento in (
            (lote.x, predio.x, e.recuo_lateral_e, "recuo_lateral_e"),
            (predio.x, predio.direita, e.largura, None),
            (predio.direita, lote.direita, p.recuo_lateral_d, "recuo_lateral_d")):
        folha.cota(inicio, y_cadeia, fim, y_cadeia, valor, "", elemento)
    folha.cota(lote.x, y_cadeia + 7, lote.direita, y_cadeia + 7, t.testada, "", "testada")

    desenhar_area_permeavel(folha, lote, predio, k)
    desenhar_norte(folha, principal.x + 15, principal.topo - 20)

    base_quadro = desenhar_quadro(folha, coluna.x, coluna.topo - 2, min(coluna.largura, 115))
    desenhar_localizacao(folha, Retangulo(coluna.x, coluna.y, coluna.largura,
                                          base_quadro - coluna.y - 8))


def area_de_desenho(folha: Folha, principal: Retangulo, coluna: Retangulo) -> Retangulo:
    """Área livre para as folhas 02 e 03.

    Nos carimbos 0 e 3, a coluna lateral fica acima do carimbo: usar só a área principal,
    senão o desenho passa por baixo do carimbo.
    """
    if folha.v.estilo_carimbo in (0, 3):
        return principal
    return Retangulo(principal.x, principal.y, principal.largura + coluna.largura,
                     principal.altura)


# ---------------------------------------------------------------- folha 02: plantas baixas

# (nome, x0, y0, x1, y1 em fração da largura/profundidade, y=0 na frente; nível; molhado;
#  mobiliário)
AMBIENTES_TERREO = (
    ("Garagem", 0, 0, .45, .38, 0.00, False, "carro"),
    ("Sala de estar", .45, 0, 1, .38, 0.15, False, "sofa"),
    ("Escada", 0, .38, .22, .66, None, False, "escada"),
    ("Lavabo", .22, .38, .45, .66, 0.15, True, "banheiro"),
    ("Cozinha", .45, .38, 1, .66, 0.15, True, "cozinha"),
    ("Área de serviço", 0, .66, .45, 1, 0.13, True, "tanque"),
    ("Jantar", .45, .66, 1, 1, 0.15, False, "mesa"),
)
AMBIENTES_SUPERIOR = (
    ("Suíte", 0, 0, .55, .38, 3.02, False, "cama_casal"),
    ("Dormitório 1", .55, 0, 1, .38, 3.02, False, "cama_solteiro"),
    ("Escada", 0, .38, .22, .66, None, False, "escada"),
    ("Banho", .22, .38, .45, .66, 3.02, True, "banheiro_chuveiro"),
    ("Circulação", .45, .38, 1, .66, 3.02, False, None),
    ("Dormitório 2", 0, .66, .55, 1, 3.02, False, "cama_solteiro"),
    ("Banho suíte", .55, .66, 1, 1, 3.02, True, "banheiro_chuveiro"),
)
TAMANHO_MOBILIA = {"carro": (1.8, 4.3), "sofa": (2.1, 0.85), "mesa": (1.6, 1.8),
                   "cozinha": (2.4, 0.6), "tanque": (0.6, 0.55), "cama_casal": (1.6, 2.0),
                   "cama_solteiro": (0.9, 2.0)}
ESQUADRIAS = (
    ("P1", "0,90 x 2,10", "Porta de giro — entrada"),
    ("P2", "0,80 x 2,10", "Porta de giro — madeira"),
    ("P3", "0,70 x 2,10", "Porta de giro — áreas molhadas"),
    ("PG", "2,80 x 2,20", "Portão basculante"),
    ("J1", "1,50 x 1,20", "Janela de correr — peitoril 1,00"),
    ("J2", "0,60 x 0,60", "Basculante — peitoril 1,60"),
)


def desenhar_planta(folha: Folha, x0: float, y0: float, k: float, ambientes, terreo: bool):
    e = folha.p.edificacao
    largura, profundidade = e.largura * k, e.profundidade * k
    te, ti = 0.20 * k, 0.15 * k

    def celula(a):
        return Retangulo(x0 + a[1] * largura, y0 + a[2] * profundidade,
                         (a[3] - a[1]) * largura, (a[4] - a[2]) * profundidade)

    def interno(a):
        c = celula(a)
        esq = te if a[1] == 0 else ti / 2
        dir_ = te if a[3] == 1 else ti / 2
        baixo = te if a[2] == 0 else ti / 2
        cima = te if a[4] == 1 else ti / 2
        return Retangulo(c.x + esq, c.y + baixo, c.largura - esq - dir_,
                         c.altura - baixo - cima)

    # Pisos molhados e mobiliário (por baixo das paredes)
    for a in ambientes:
        r = interno(a)
        nome, nivel_m, molhado, mobilia = a[0], a[5], a[6], a[7]
        if molhado:
            blocos.hachura_piso(folha, r, k)
        if mobilia == "escada":
            blocos.escada(folha, r, k, sobe=terreo)
        elif mobilia in ("banheiro", "banheiro_chuveiro"):
            blocos.banheiro(folha, r, k, com_chuveiro=mobilia == "banheiro_chuveiro")
        elif mobilia:
            w, d = TAMANHO_MOBILIA[mobilia]
            if w * k < r.largura - 2 and d * k < r.altura - 8:
                blocos.MOBILIA[mobilia](folha, r.x + r.largura / 2, r.y + r.altura * 0.42, k)
        # Rótulo: nome, área útil e nível
        cy = r.topo - folha.altura_texto(0.75) - 1.5
        folha.texto(r.x + r.largura / 2, cy, folha.rotulo(nome), escala=0.75, negrito=True,
                    alinhamento="centro")
        if nivel_m is not None:
            area = (r.largura / k) * (r.altura / k)
            folha.texto(r.x + r.largura / 2, cy - folha.altura_texto(0.65) - 1,
                        f"A = {formatar_numero(area)} m²", escala=0.65, alinhamento="centro")
            folha.texto(r.x + r.largura / 2, cy - 2 * folha.altura_texto(0.65) - 2,
                        f"+{formatar_numero(nivel_m)}", escala=0.6, alinhamento="centro")

    # Paredes externas e internas
    for r in (Retangulo(x0, y0, largura, te), Retangulo(x0, y0 + profundidade - te, largura, te),
              Retangulo(x0, y0, te, profundidade), Retangulo(x0 + largura - te, y0, te,
                                                                 profundidade)):
        blocos.parede(folha, r)
    for fracao in (.38, .66):
        blocos.parede(folha, Retangulo(x0, y0 + fracao * profundidade - ti / 2, largura, ti))
    for a in ambientes:
        if a[1] > 0:
            c = celula(a)
            blocos.parede(folha, Retangulo(c.x - ti / 2, c.y, ti, c.altura))
    folha.retangulo(Retangulo(x0, y0, largura, profundidade), PENA_GROSSA)

    # Portas e janelas
    for a in ambientes:
        c = celula(a)
        nome, molhado, mobilia = a[0], a[6], a[7]
        porta_m = 0.7 if molhado else 0.8
        rotulo_porta = "P3" if molhado else "P2"
        if mobilia == "escada" or nome in ("Cozinha", "Circulação"):
            pass
        elif a[2] == 0:
            blocos.porta(folha, c.x + 0.3 * k, c.topo, porta_m * k, ti, True, -1, rotulo_porta)
        elif a[4] == 1:
            blocos.porta(folha, c.x + 0.3 * k, c.y, porta_m * k, ti, True, 1, rotulo_porta)
        else:
            blocos.porta(folha, c.direita, c.y + 0.3 * k, porta_m * k, ti, False, -1,
                         rotulo_porta)
        # Janelas nas paredes externas
        if a[2] == 0 and not (terreo and nome == "Garagem"):
            comprimento = min(1.5 * k, c.largura * 0.4)
            x = c.x + c.largura * 0.55 if (terreo and nome == "Sala de estar") else \
                c.x + (c.largura - comprimento) / 2
            blocos.janela(folha, x, y0 + te / 2, comprimento, te, True, "J1", -1)
        elif a[4] == 1:
            comprimento = min((0.6 if molhado else 1.5) * k, c.largura * 0.4)
            blocos.janela(folha, c.x + (c.largura - comprimento) / 2, y0 + profundidade - te / 2,
                          comprimento, te, True, "J2" if molhado else "J1", 1)
        elif a[3] == 1 and nome == "Cozinha":
            comprimento = min(1.2 * k, c.altura * 0.5)
            blocos.janela(folha, x0 + largura - te / 2, c.y + (c.altura - comprimento) / 2,
                          comprimento, te, False, "J1", 1)

    if terreo:  # entrada social e portão da garagem
        sala = celula(AMBIENTES_TERREO[1])
        blocos.porta(folha, sala.x + 0.4 * k, y0 + te / 2, 0.9 * k, te, True, 1, "P1")
        garagem = celula(AMBIENTES_TERREO[0])
        vao = Retangulo(garagem.x + 0.35 * k, y0, garagem.largura - 0.6 * k, te)
        blocos.vao_branco(folha, vao)
        folha.tracejada(vao.x, y0 + te / 2, vao.direita, y0 + te / 2, PENA_MEDIA)
        folha.texto(vao.x + vao.largura / 2, y0 - 4, "PG", escala=0.6, alinhamento="centro")

    # Pilares nos cantos e no vão da garagem
    for fx in (0, .45, 1):
        for fy in (0, .38, .66, 1):
            px = x0 + min(max(fx * largura, te / 2), largura - te / 2)
            py = y0 + min(max(fy * profundidade, te / 2), profundidade - te / 2)
            blocos.pilar(folha, px, py, k)

    # Cotas internas (encadeadas) — números que não são recuos
    for inicio, fim in ((0, .38), (.38, .66), (.66, 1)):
        folha.cota(x0 + largura + 6, y0 + inicio * profundidade, x0 + largura + 6,
                   y0 + fim * profundidade, (fim - inicio) * e.profundidade, "", None)
    divisao = .45 if terreo else .55
    for inicio, fim in ((0, divisao), (divisao, 1)):
        folha.cota(x0 + inicio * largura, y0 + profundidade + 6, x0 + fim * largura,
                   y0 + profundidade + 6, (fim - inicio) * e.largura, "", None)


def quadro_esquadrias(folha: Folha, x: float, topo: float):
    altura = folha.altura_texto(0.7) + 2
    folha.texto(x, topo - altura, folha.rotulo("Quadro de esquadrias"), escala=0.8, negrito=True)
    y = topo - altura
    for codigo, dimensao, descricao in ESQUADRIAS:
        y -= altura
        folha.texto(x, y, codigo, escala=0.7, negrito=True)
        folha.texto(x + 10, y, dimensao, escala=0.7)
        folha.texto(x + 32, y, folha.rotulo(descricao), escala=0.7)


def dividir_em_dois(area: Retangulo, largura_m: float, altura_m: float, folga_mm: float,
                    reserva_titulo: float = 30.0) -> tuple[int, list[Retangulo]]:
    """Divide a área para duas vistas: lado a lado ou empilhadas (a primeira em cima).

    Escolhe o arranjo que permite a maior escala de desenho.
    """
    lado_a_lado = [Retangulo(area.x + i * area.largura / 2, area.y, area.largura / 2,
                             area.altura) for i in range(2)]
    empilhado = [Retangulo(area.x, area.y + (1 - i) * area.altura / 2, area.largura,
                           area.altura / 2) for i in range(2)]
    opcoes = []
    for partes in (lado_a_lado, empilhado):
        util = Retangulo(0, 0, partes[0].largura, partes[0].altura - reserva_titulo)
        opcoes.append((escolher_escala(largura_m, altura_m, util, folga_mm), partes))
    return min(opcoes, key=lambda opcao: opcao[0])


def folha_plantas(folha: Folha, indice: int):
    e = folha.p.edificacao
    principal, coluna = regioes(folha, indice, folha.rotulo("Plantas baixas"))
    folha.texto(principal.x + 2, principal.topo - 4, MARCA_FICTICIO, escala=0.6)
    area_total = area_de_desenho(folha, principal, coluna)
    quadro_esquadrias(folha, area_total.x + 2, area_total.topo - 8)
    area_plantas = Retangulo(area_total.x, area_total.y, area_total.largura,
                             area_total.altura - 40)
    escala, partes = dividir_em_dois(area_plantas, e.largura, e.profundidade, folga_mm=55)
    k = 1000 / escala
    nomes = (folha.rotulo("Planta baixa — térreo"),
             folha.rotulo("Planta baixa — pavimento superior"))
    for i, (nome, area, ambientes, parte) in enumerate(zip(
            nomes, e.areas_pavimentos, (AMBIENTES_TERREO, AMBIENTES_SUPERIOR), partes,
            strict=True)):
        x0 = parte.x + (parte.largura - e.largura * k) / 2
        y0 = parte.y + 28 + max(0.0, (parte.altura - 40 - e.profundidade * k) / 2)
        desenhar_planta(folha, x0, y0, k, ambientes, terreo=i == 0)
        folha.cota(x0, y0 - 8, x0 + e.largura * k, y0 - 8, e.largura, "", None)
        folha.cota(x0 - 8, y0, x0 - 8, y0 + e.profundidade * k, e.profundidade, "", None)
        folha.texto(x0, y0 - 18, f"{nome} — {folha.rotulo('Escala')} 1:{escala}", negrito=True)
        folha.texto(x0, y0 - 23, f"{folha.rotulo('Área')}: {formatar_numero(area)} m²",
                    escala=0.9)


# ---------------------------------------------------------------- folha 03: corte e fachada

CONTRAPISO, PE_DIREITO_1, LAJE, PE_DIREITO_2 = 0.10, 2.80, 0.12, 2.70
TOPO_LAJE = CONTRAPISO + PE_DIREITO_1 + LAJE + PE_DIREITO_2 + LAJE
BEIRAL = 0.6


def desenhar_corte(folha: Folha, x0: float, solo: float, k: float):
    e = folha.p.edificacao
    blocos.linha_de_terra(folha, x0 - 10, x0 + (e.profundidade + 5) * k, solo)

    # Muro na divisa frontal
    muro = Retangulo(x0, solo, 0.15 * k + 0.4, e.muro_altura * k)
    blocos.parede(folha, muro)
    folha.texto(x0 + 1.5, solo + e.muro_altura * k + 2, folha.rotulo("Muro"), escala=0.7)
    folha.cota(x0 - 6, solo, x0 - 6, solo + e.muro_altura * k, e.muro_altura, "Muro", "muro")
    blocos.pessoa(folha, x0 + 1.4 * k, solo, k)

    px, largura = x0 + 3 * k, e.profundidade * k
    parede = 0.2 * k
    y_laje1 = solo + (CONTRAPISO + PE_DIREITO_1) * k
    y_laje2 = y_laje1 + (LAJE + PE_DIREITO_2) * k
    y_topo = solo + TOPO_LAJE * k
    blocos.parede(folha, Retangulo(px, solo, largura, CONTRAPISO * k))
    for y in (y_laje1, y_laje2):
        blocos.parede(folha, Retangulo(px, y, largura, LAJE * k))
        for x in (px, px + largura / 2 - 0.075 * k, px + largura - parede):
            blocos.parede(folha, Retangulo(x, y - 0.3 * k, parede, 0.3 * k))
    for x in (px, px + largura - parede):
        blocos.parede(folha, Retangulo(x, solo, parede, TOPO_LAJE * k))
    # Janelas cortadas na fachada frontal (vão na parede)
    for piso in (solo + CONTRAPISO * k, y_laje1 + LAJE * k):
        vao = Retangulo(px, piso + 1.0 * k, parede, 1.2 * k)
        blocos.vao_branco(folha, vao)
        for dx in (0.3, 0.5, 0.7):
            folha.linha(px + parede * dx, vao.y, px + parede * dx, vao.topo, PENA_FINA)
    # Telhado em duas águas (cumeeira paralela à frente)
    cumeeira = (px + largura / 2, solo + e.altura * k)
    for deslocamento in (0, 0.15 * k):
        folha.poligono([(px - BEIRAL * k, y_topo + deslocamento),
                        (cumeeira[0], cumeeira[1] + deslocamento),
                        (px + largura + BEIRAL * k, y_topo + deslocamento)],
                       PENA_GROSSA if deslocamento else PENA_MEDIA, fechado=False)
    blocos.chamada(folha, px + largura * 0.7, (y_topo + cumeeira[1]) / 2 + 1,
                   px + largura * 0.85, cumeeira[1] + 6, folha.rotulo("Telha cerâmica i=30%"))
    blocos.chamada(folha, px + largura * 0.3, y_laje1 + LAJE * k / 2, px + largura * 0.15,
                   y_laje1 - 8, folha.rotulo("Laje maciça e=12 cm"))
    folha.texto(px + largura / 2, solo + 1.3 * k, folha.rotulo("Sala"), escala=0.75,
                alinhamento="centro")
    folha.texto(px + largura / 2, y_laje1 + 1.6 * k, folha.rotulo("Suíte"), escala=0.75,
                alinhamento="centro")
    blocos.pessoa(folha, px + largura * 0.3, solo + CONTRAPISO * k, k)

    # Cotas e níveis
    direita = px + largura
    folha.cota(direita + 5, solo + CONTRAPISO * k, direita + 5, y_laje1, PE_DIREITO_1,
               "Pé-direito", None)
    folha.cota(direita + 5, y_laje1 + LAJE * k, direita + 5, y_laje2, PE_DIREITO_2,
               "Pé-direito", None)
    folha.cota(direita + 12, solo, direita + 12, cumeeira[1], e.altura, "Altura total",
               "altura_total")
    for y, valor in ((solo, 0.0), (y_laje1 + LAJE * k,
                                   CONTRAPISO + PE_DIREITO_1 + LAJE),
                     (y_topo, TOPO_LAJE)):
        blocos.nivel(folha, direita + 18, y, valor)


def desenhar_fachada(folha: Folha, fx: float, solo: float, k: float):
    e = folha.p.edificacao
    largura = e.largura * k
    y_topo = solo + TOPO_LAJE * k
    blocos.linha_de_terra(folha, fx - 10, fx + largura + 10, solo)
    folha.retangulo(Retangulo(fx, solo, largura, TOPO_LAJE * k), PENA_MEDIA)
    folha.linha(fx, solo + 3.02 * k, fx + largura, solo + 3.02 * k, PENA_FINA)  # friso
    telhado = Retangulo(fx - BEIRAL * k, y_topo, largura + 2 * BEIRAL * k,
                        (e.altura - TOPO_LAJE) * k)
    folha.retangulo(telhado, PENA_MEDIA)
    y = telhado.y + 0.25 * k
    while y < telhado.topo:
        folha.linha(telhado.x, y, telhado.direita, y, 0.08)
        y += 0.25 * k
    largura_portao = min(2.8, e.largura * 0.45 - 0.6) * k
    blocos.portao(folha, Retangulo(fx + 0.35 * k, solo, largura_portao, 2.2 * k), k)
    x_porta = fx + e.largura * 0.45 * k + 0.4 * k
    folha.retangulo(Retangulo(x_porta, solo, 0.9 * k, 2.1 * k), PENA_MEDIA)
    blocos.esquadria_vista(folha, Retangulo(fx + largura - 1.9 * k, solo + 1.0 * k, 1.5 * k,
                                            1.2 * k))
    for fracao in (0.12, 0.62):
        blocos.esquadria_vista(folha, Retangulo(fx + largura * fracao, solo + 4.1 * k,
                                                min(1.2 * k, largura * 0.3), 1.0 * k))
    blocos.pessoa(folha, fx + largura + 5, solo, k)
    x_nota = fx + largura + 12
    notas = ((fx + largura * 0.5, telhado.y + telhado.altura / 2, "Telha cerâmica"),
             (fx + largura * 0.9, solo + 4.6 * k, "Esquadrias em alumínio"),
             (fx + largura * 0.95, solo + 3.6 * k, "Pintura acrílica branco gelo"),
             (fx + largura * 0.95, solo + 0.5 * k, "Revestimento cerâmico 10x10 cm"))
    for i, (x, y, texto) in enumerate(notas):
        blocos.chamada(folha, x, y, x_nota, telhado.topo + 4 - i * 7, folha.rotulo(texto))
    blocos.nivel(folha, fx - 6, solo, 0.0)
    blocos.nivel(folha, fx - 6, y_topo, TOPO_LAJE)


def folha_corte(folha: Folha, indice: int):
    e = folha.p.edificacao
    principal, coluna = regioes(folha, indice, folha.rotulo("Corte e fachada"))
    folha.texto(principal.x + 2, principal.topo - 4, MARCA_FICTICIO, escala=0.6)
    area_total = area_de_desenho(folha, principal, coluna)
    altura_vista = max(e.altura, TOPO_LAJE) + 1
    escala, (parte_corte, parte_fachada) = dividir_em_dois(
        area_total, e.profundidade + 3 + 2 * BEIRAL, altura_vista, folga_mm=60)
    k = 1000 / escala

    def solo_de(parte: Retangulo) -> float:
        return parte.y + 28 + max(0.0, (parte.altura - 40 - altura_vista * k) / 2)

    x0, solo = parte_corte.x + 25, solo_de(parte_corte)
    desenhar_corte(folha, x0, solo, k)
    folha.texto(x0, solo - 14,
                f"{folha.rotulo('Corte AA')} — {folha.rotulo('Escala')} 1:{escala}", negrito=True)
    fx, solo = parte_fachada.x + 20, solo_de(parte_fachada)
    desenhar_fachada(folha, fx, solo, k)
    folha.texto(fx, solo - 14,
                f"{folha.rotulo('Fachada frontal')} — {folha.rotulo('Escala')} 1:{escala}",
                negrito=True)


# ---------------------------------------------------------------- montagem dos arquivos

FOLHAS: tuple[Callable[[Folha, int], None], ...] = (folha_situacao, folha_plantas, folha_corte)


def _novo_canvas(projeto: Projeto) -> tuple[canvas.Canvas, io.BytesIO]:
    largura, altura = TAMANHOS_MM[projeto.variacao.formato]
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(largura * MM, altura * MM), invariant=1)
    c.setTitle(projeto.identificacao.titulo)
    c.setSubject("DOCUMENTO SINTÉTICO — base de testes do Arquiteto Auditor")
    c.setCreator(f"Gerador sintético Arquiteto Auditor (estilo {projeto.variacao.estilo_software})")
    return c, buffer


def gerar_pdfs(projeto: Projeto) -> list[tuple[str, bytes]]:
    """Gera as folhas em memória: [(nome do arquivo, bytes do PDF)]."""
    resultado = []
    if projeto.variacao.arquivo_unico:
        c, buffer = _novo_canvas(projeto)
        for indice, desenhar in enumerate(FOLHAS):
            desenhar(Folha(c, projeto), indice)
            c.showPage()
        c.save()
        resultado.append(("pranchas.pdf", buffer.getvalue()))
        return resultado
    for indice, desenhar in enumerate(FOLHAS):
        c, buffer = _novo_canvas(projeto)
        desenhar(Folha(c, projeto), indice)
        c.showPage()
        c.save()
        resultado.append((f"prancha_{indice + 1:02d}.pdf", buffer.getvalue()))
    return resultado


def desenhar_pranchas(projeto: Projeto, pasta: Path) -> list[Path]:
    """Grava as pranchas (sem assinatura) na pasta e devolve os caminhos."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for nome, conteudo in gerar_pdfs(projeto):
        caminho = pasta / nome
        caminho.write_bytes(conteudo)
        caminhos.append(caminho)
    return caminhos
