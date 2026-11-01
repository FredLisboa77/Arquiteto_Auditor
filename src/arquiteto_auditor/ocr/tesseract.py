"""OCR com Tesseract: imagem → palavras com posição (bbox) e confiança.

Pré-processamento (pensado nos escaneados reais, docs/06 §5 e §6):
1. tons de cinza;
2. ampliação para ~300 dpi quando a imagem tem resolução menor (o código de obras real tem
   135 dpi; o Tesseract erra muito abaixo de ~200 dpi);
3. linhas retas longas apagadas (grade de tabelas);
4. correção da inclinação (até ±5°), medida pelo perfil das linhas de texto.

Segmentação "coluna única" (psm 4): os documentos lidos por OCR (matrícula, escritura, lei,
norma, quadros) são de uma coluna. A automática (psm 3) se perde com as faixas decorativas
do papel de segurança das certidões e lê o texto fora de ordem.

As posições devolvidas estão no sistema da imagem ORIGINAL (desfeitas a ampliação e a rotação).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np
import pytesseract
from PIL import Image

from arquiteto_auditor.config import ConfigOCR, config_ocr

VERSAO = "2"  # mude quando o pré-processamento mudar: invalida o cache


class OCRIndisponivel(RuntimeError):
    pass


@dataclass(frozen=True)
class PalavraOCR:
    texto: str
    bbox: tuple[float, float, float, float]  # pixels da imagem original
    confianca: float  # 0 a 1
    bloco: int
    linha: int


def estimar_inclinacao(cinza: np.ndarray, limite: float = 5.0, passo: float = 0.1) -> float:
    """Ângulo (graus, anti-horário) que deixa as linhas de texto mais horizontais."""
    reduzida = Image.fromarray(cinza).reduce(max(1, cinza.shape[1] // 800))
    tinta = (np.asarray(reduzida, dtype=np.float32) < 128).astype(np.uint8) * 255
    imagem = Image.fromarray(tinta)
    melhor, melhor_angulo = -1.0, 0.0
    for angulo in np.arange(-limite, limite + passo / 2, passo):
        perfil = np.asarray(imagem.rotate(-angulo, resample=Image.BILINEAR),
                            dtype=np.float64).sum(axis=1)
        nitidez = float(np.var(np.diff(perfil)))
        if nitidez > melhor:
            melhor, melhor_angulo = nitidez, float(angulo)
    return round(melhor_angulo, 1)


def _girar_ponto(x: float, y: float, cx: float, cy: float, graus: float) -> tuple[float, float]:
    """Gira (x, y) em torno de (cx, cy) no sentido anti-horário da imagem (y para baixo)."""
    seno, cosseno = math.sin(math.radians(graus)), math.cos(math.radians(graus))
    dx, dy = x - cx, y - cy
    return cx + dx * cosseno + dy * seno, cy - dx * seno + dy * cosseno


def apagar_grade(cinza: Image.Image, fracao: float = 0.6) -> Image.Image:
    """Apaga linhas retas longas (grade de tabelas, réguas) antes do OCR.

    Uma fileira (ou coluna) de pixels com tinta em mais de `fracao` da largura (ou altura) é
    linha, não texto: o texto tem espaços entre letras e palavras. Com a grade, o Tesseract
    trata cada célula como figura e não lê nada (quadro de áreas colado como imagem no
    memorial — docs/06 §6.2). A fileira vizinha também é apagada (borda suavizada da linha).
    """
    pixels = np.asarray(cinza).copy()
    tinta = pixels < 160
    fileiras = np.flatnonzero(tinta.mean(axis=1) > fracao)
    colunas = np.flatnonzero(tinta.mean(axis=0) > fracao)
    for deslocamento in (-1, 0, 1):
        pixels[np.clip(fileiras + deslocamento, 0, pixels.shape[0] - 1), :] = 255
        pixels[:, np.clip(colunas + deslocamento, 0, pixels.shape[1] - 1)] = 255
    return Image.fromarray(pixels)


def ler_imagem(imagem: Image.Image, dpi: int, config: ConfigOCR | None = None,
               corrigir_inclinacao: bool = True) -> list[PalavraOCR]:
    """Lê as palavras de uma imagem (página escaneada ou recorte) com o Tesseract."""
    config = config or config_ocr()
    if not config.tesseract_cmd:
        raise OCRIndisponivel("Tesseract não encontrado (ver docs/03-arquitetura.md §6.2)")
    pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
    # Pela variável de ambiente: "--tessdata-dir" quebra com espaços no caminho (Windows).
    os.environ["TESSDATA_PREFIX"] = str(config.tessdata_dir)

    cinza = imagem.convert("L")
    fator = max(1.0, config.dpi / dpi)
    if fator > 1.05:
        cinza = cinza.resize((round(cinza.width * fator), round(cinza.height * fator)),
                             Image.LANCZOS)
    cinza = apagar_grade(cinza)
    angulo = estimar_inclinacao(np.asarray(cinza)) if corrigir_inclinacao else 0.0
    if angulo:
        cinza = cinza.rotate(-angulo, resample=Image.BICUBIC, fillcolor=255)

    dados = pytesseract.image_to_data(
        cinza, lang=config.idioma, output_type=pytesseract.Output.DICT,
        config="--oem 1 --psm 4")
    cx, cy = cinza.width / 2, cinza.height / 2
    palavras = []
    for i, texto in enumerate(dados["text"]):
        texto = texto.strip()
        confianca = float(dados["conf"][i])
        if not texto or confianca < 0:
            continue
        x, y, w, h = (dados[k][i] for k in ("left", "top", "width", "height"))
        cantos = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
        if angulo:  # desfaz a correção de inclinação
            cantos = [_girar_ponto(px, py, cx, cy, angulo) for px, py in cantos]
        xs, ys = [c[0] / fator for c in cantos], [c[1] / fator for c in cantos]
        palavras.append(PalavraOCR(
            texto=texto, bbox=(min(xs), min(ys), max(xs), max(ys)),
            confianca=round(confianca / 100, 3), bloco=int(dados["block_num"][i]),
            linha=int(dados["par_num"][i]) * 1000 + int(dados["line_num"][i])))
    return palavras
