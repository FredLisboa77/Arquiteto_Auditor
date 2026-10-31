"""Calibração com documentos ESCANEADOS reais — mede a imagem e mascara o conteúdo.

Uso:  .venv\\Scripts\\python scripts\\mascarar_escaneado.py [pasta ou arquivo]
      (padrão: dados_privados\\desenvolvimento)

Para cada PDF (identificado só como "documento N"):
1. Mostra ESTATÍSTICAS da imagem de cada página (sem conteúdo): resolução, compressão, cor,
   tom do papel, ruído, tinta, presença de cor (carimbos), inclinação, margens, entrelinha,
   altura das letras e se o texto é justificado.
2. Grava em dados_privados\\cache\\mascarado\\escaneado_N_pagM.png uma versão MASCARADA:
   cada palavra vira uma barra (cinza ou na cor da tinta), sobre um papel liso com o mesmo
   tom e ruído do original. Fica visível só o desenho da página (colunas, molduras, carimbos,
   selos, assinaturas), nunca o texto.

CONFIRA as imagens mascaradas antes de compartilhá-las.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = RAIZ / "dados_privados" / "desenvolvimento"
PASTA_SAIDA = RAIZ / "dados_privados" / "cache" / "mascarado"
DPI_ANALISE = 150  # resolução usada para medir
DPI_MASCARA = 100  # resolução da imagem mascarada
MM_POR_POLEGADA = 25.4


# ---------------------------------------------------------------- utilitários de imagem


def media_movel(matriz: np.ndarray, raio_x: int, raio_y: int) -> np.ndarray:
    """Média de cada pixel com a vizinhança (2·raio+1 pixels em cada direção)."""
    resultado = matriz.astype(np.float64)
    for eixo, raio in ((1, raio_x), (0, raio_y)):
        if raio <= 0:
            continue
        preenchido = np.pad(resultado, [(raio + 1, raio) if e == eixo else (0, 0)
                                        for e in range(resultado.ndim)], mode="edge")
        soma = np.cumsum(preenchido, axis=eixo)
        fim = np.take(soma, range(2 * raio + 1, soma.shape[eixo]), axis=eixo)
        inicio = np.take(soma, range(0, soma.shape[eixo] - 2 * raio - 1), axis=eixo)
        resultado = (fim - inicio) / (2 * raio + 1)
    return resultado


def dilatar(mascara: np.ndarray, raio_x: int, raio_y: int) -> np.ndarray:
    """Engorda as áreas marcadas (junta as letras de uma palavra numa barra só)."""
    return media_movel(mascara.astype(np.float64), raio_x, raio_y) > 1e-9


def quadricular(mascara: np.ndarray, altura: int, largura: int,
                densidade: float = 0.0) -> np.ndarray:
    """Preenche blocos inteiros (altura × largura px) com mais que `densidade` de pixels marcados.

    Apaga o contorno das letras (hastes que sobem e descem têm pouca tinta e somem), que
    poderia deixar adivinhar as palavras: sobra só o tamanho e a posição de cada palavra.
    """
    linhas, colunas = mascara.shape
    preenchida = np.zeros((-(-linhas // altura) * altura, -(-colunas // largura) * largura), bool)
    preenchida[:linhas, :colunas] = mascara
    blocos = preenchida.reshape(preenchida.shape[0] // altura, altura,
                                preenchida.shape[1] // largura, largura).mean(axis=(1, 3))
    blocos = blocos > densidade
    return np.repeat(np.repeat(blocos, altura, axis=0), largura, axis=1)[:linhas, :colunas]


def luminancia(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def saturacao(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=-1) - rgb.min(axis=-1)


def estimar_inclinacao(tinta: np.ndarray, limite: float = 5.0, passo: float = 0.1) -> float:
    """Ângulo (graus) que deixa as linhas de texto mais "horizontais" (perfil mais contrastado).

    Positivo = texto girado no sentido anti-horário.
    """
    imagem = Image.fromarray((tinta * 255).astype(np.uint8))
    melhor, melhor_angulo = -1.0, 0.0
    for angulo in np.arange(-limite, limite + passo / 2, passo):
        girada = np.asarray(imagem.rotate(-angulo, resample=Image.BILINEAR), dtype=np.float64)
        perfil = girada.sum(axis=1)
        nitidez = float(np.var(np.diff(perfil)))
        if nitidez > melhor:
            melhor, melhor_angulo = nitidez, float(angulo)
    return round(melhor_angulo, 1)


_MATIZES = ((0, "vermelho"), (30, "laranja/marrom"), (60, "amarelo"), (120, "verde"),
            (180, "ciano"), (225, "azul"), (275, "roxo"), (320, "rosa"), (360, "vermelho"))


def nome_da_matiz(rgb: np.ndarray) -> str:
    r, g, b = (float(c) for c in rgb)
    maior, menor = max(r, g, b), min(r, g, b)
    if maior - menor < 1:
        return "cinza"
    if maior == r:
        matiz = (60 * (g - b) / (maior - menor)) % 360
    elif maior == g:
        matiz = 60 * (b - r) / (maior - menor) + 120
    else:
        matiz = 60 * (r - g) / (maior - menor) + 240
    return min(_MATIZES, key=lambda par: abs(par[0] - matiz))[1]


# ---------------------------------------------------------------- análise de uma página


@dataclass
class AnalisePagina:
    linhas: list[str]  # estatísticas legíveis
    mascarada: Image.Image


def _intervalos(ativos: np.ndarray) -> list[tuple[int, int]]:
    """Trechos contínuos de True num vetor: [(início, fim), ...]."""
    bordas = np.diff(np.concatenate([[0], ativos.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(bordas == 1), np.flatnonzero(bordas == -1), strict=True))


def analisar_pagina(rgb: np.ndarray, dpi: int) -> AnalisePagina:
    mm = MM_POR_POLEGADA / dpi  # mm por pixel
    lum = luminancia(rgb)
    sat = saturacao(rgb)
    papel_lum = float(np.percentile(lum, 75))
    tinta = lum < papel_lum - 45
    fundo = lum > papel_lum - 20
    papel = np.median(rgb[fundo], axis=0)
    ruido = float(np.std(lum[fundo & (lum < papel_lum + 25)]))
    colorida = tinta & (sat > 50)

    linhas = [
        f"papel: RGB {tuple(int(c) for c in papel)} | ruído do fundo: {ruido:.1f}",
        f"tinta: {tinta.mean() * 100:.1f}% da folha | tom típico da tinta (lum. 0–255): "
        f"{np.percentile(lum[tinta], 50) if tinta.any() else 0:.0f}",
    ]
    if colorida.sum() > 0.0005 * tinta.size:
        cor = np.median(rgb[colorida], axis=0)
        linhas.append(f"tinta colorida: {colorida.mean() * 100:.2f}% da folha, "
                      f"predominante {nome_da_matiz(cor)} RGB {tuple(int(c) for c in cor)}")
    else:
        linhas.append("tinta colorida: praticamente nenhuma")

    if tinta.any():
        inclinacao = estimar_inclinacao(tinta[::2, ::2])
        linhas.append(f"inclinação estimada: {inclinacao:+.1f}°")
        endireitada = np.asarray(
            Image.fromarray(tinta.astype(np.uint8) * 255).rotate(-inclinacao), dtype=bool)
        colunas_com_tinta = np.flatnonzero(endireitada.mean(axis=0) > 0.01)
        linhas_com_tinta = np.flatnonzero(endireitada.mean(axis=1) > 0.01)
        if colunas_com_tinta.size and linhas_com_tinta.size:
            altura, largura = endireitada.shape
            linhas.append(
                f"margens (mm): esq {colunas_com_tinta[0] * mm:.0f} · dir "
                f"{(largura - colunas_com_tinta[-1]) * mm:.0f} · sup "
                f"{linhas_com_tinta[0] * mm:.0f} · inf {(altura - linhas_com_tinta[-1]) * mm:.0f}")
        linhas.extend(_medidas_das_linhas(endireitada, mm))

    return AnalisePagina(linhas, mascarar(rgb, tinta, colorida, papel, ruido, dpi))


def _medidas_das_linhas(tinta: np.ndarray, mm: float) -> list[str]:
    """Entrelinha, altura das letras e alinhamento à direita das linhas de texto."""
    perfil = tinta.mean(axis=1)
    faixas = [(a, b) for a, b in _intervalos(perfil > 0.01) if 1.2 < (b - a) * mm < 8]
    if len(faixas) < 3:
        return ["linhas de texto: poucas para medir"]
    alturas = np.array([(b - a) * mm for a, b in faixas])
    passos = np.diff([(a + b) / 2 for a, b in faixas]) * mm
    passos = passos[passos < 15]
    fins = []
    for a, b in faixas:
        colunas = np.flatnonzero(tinta[a:b].any(axis=0))
        fins.append(colunas[-1] * mm)
    fins = np.array(fins)
    margem_direita = np.median(fins)  # sujeira e rubricas não deslocam a mediana
    cheias = np.abs(fins - margem_direita) <= 2
    return [
        f"linhas de texto: {len(faixas)} | altura da faixa da linha: mediana "
        f"{np.median(alturas):.1f} mm | entrelinha: mediana "
        f"{np.median(passos) if passos.size else 0:.1f} mm",
        f"alinhamento à direita: {cheias.mean() * 100:.0f}% das linhas terminam a até 2 mm da "
        f"mesma posição (alto = texto justificado)",
    ]


def mascarar(rgb: np.ndarray, tinta: np.ndarray, colorida: np.ndarray, papel: np.ndarray,
             ruido: float, dpi: int) -> Image.Image:
    """Troca cada palavra por uma barra, sobre um papel liso (não sobra nenhum traço original)."""
    px_por_mm = dpi / MM_POR_POLEGADA
    # junta as letras (inclusive as de fonte grande) numa barra por palavra
    raio_x, raio_y = round(1.5 * px_por_mm), round(0.3 * px_por_mm)
    bloco = (round(1.2 * px_por_mm), round(1.5 * px_por_mm))  # altura, largura
    barras = quadricular(dilatar(tinta, raio_x, raio_y), *bloco, densidade=0.25)
    barras_coloridas = quadricular(dilatar(colorida, raio_x, raio_y), *bloco, densidade=0.25)

    gerador = np.random.default_rng(0)
    saida = np.broadcast_to(papel, rgb.shape).astype(np.float64).copy()
    saida += gerador.normal(0, ruido, rgb.shape[:2])[..., None]
    saida[barras] = (95, 95, 95)
    if barras_coloridas.any():
        # cor média da tinta colorida na vizinhança (o carimbo azul vira barra azul)
        soma = np.stack([media_movel(np.where(colorida, rgb[..., c], 0), 3 * raio_x, raio_x)
                         for c in range(3)], axis=-1)
        contagem = media_movel(colorida.astype(np.float64), 3 * raio_x, raio_x)[..., None]
        cor = soma / np.maximum(contagem, 1e-9)
        saida[barras_coloridas] = cor[barras_coloridas]
    imagem = Image.fromarray(saida.clip(0, 255).astype(np.uint8))
    escala = DPI_MASCARA / dpi
    # vizinho mais próximo: não mistura tons (nenhum resquício do original nas bordas)
    return imagem.resize((round(imagem.width * escala), round(imagem.height * escala)),
                         Image.NEAREST)


# ---------------------------------------------------------------- documento


def _descricao_imagem(documento: pymupdf.Document, pagina: pymupdf.Page) -> str:
    imagens = pagina.get_images(full=True)
    if not imagens:
        return "sem imagem"
    xref = max(imagens, key=lambda i: i[2] * i[3])[0]
    info = documento.extract_image(xref)
    largura_pol = pagina.rect.width / 72
    cores = {1: "cinza", 3: "colorida", 4: "CMYK"}.get(info.get("colorspace"), "?")
    if info.get("bpc") == 1:
        cores = "preto e branco (1 bit)"
    return (f"imagem {info['width']}×{info['height']} px ≈ {info['width'] / largura_pol:.0f} dpi"
            f" | {cores} | compressão {info['ext']} | {len(info['image']) // 1024} KB"
            f" | {len(imagens)} imagem(ns) na página")


def analisar_documento(caminho: Path, numero: int, destino: Path) -> list[str]:
    saida = []
    with pymupdf.open(caminho) as documento:
        saida.append(f"documento {numero}: {len(documento)} página(s)")
        for indice, pagina in enumerate(documento, start=1):
            largura = pagina.rect.width * MM_POR_POLEGADA / 72
            altura = pagina.rect.height * MM_POR_POLEGADA / 72
            texto = len(pagina.get_text().strip())
            saida.append(f"  pág. {indice}: {largura:.0f}×{altura:.0f} mm | texto selecionável: "
                         f"{texto} caracteres | {_descricao_imagem(documento, pagina)}")
            pixmap = pagina.get_pixmap(dpi=DPI_ANALISE, colorspace=pymupdf.csRGB, alpha=False)
            rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, 3).astype(np.float64)
            analise = analisar_pagina(rgb, DPI_ANALISE)
            saida.extend(f"      {linha}" for linha in analise.linhas)
            arquivo = destino / f"escaneado_{numero}_pag{indice}.png"
            analise.mascarada.save(arquivo)
            saida.append(f"      máscara → {arquivo.relative_to(RAIZ)}")
    return saida


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    origem = Path(argumentos[0]) if argumentos else PASTA_PADRAO
    arquivos = [origem] if origem.is_file() else sorted(origem.rglob("*.pdf"))
    if not arquivos:
        print(f"Nenhum PDF encontrado em {origem}")
        return 1
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    indice = []
    for numero, caminho in enumerate(arquivos, start=1):
        try:
            print("\n".join(analisar_documento(caminho, numero, PASTA_SAIDA)))
        except Exception as erro:  # arquivo corrompido, protegido por senha etc.
            print(f"documento {numero}: não foi possível ler ({type(erro).__name__})")
            continue
        indice.append(f"escaneado_{numero}_* = {caminho}")
    (PASTA_SAIDA / "indice_escaneados.txt").write_text("\n".join(indice) + "\n",
                                                       encoding="utf-8")
    print("\nConfira as imagens mascaradas antes de compartilhar. indice_escaneados.txt (com os "
          "nomes reais dos arquivos) é só para você.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
