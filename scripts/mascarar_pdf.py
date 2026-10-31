"""Mascaramento de PDFs reais para calibração — mostra o LAYOUT, esconde os dados pessoais.

Uso:  .venv\\Scripts\\python scripts\\mascarar_pdf.py [pasta ou arquivo]
      (padrão: dados_privados\\desenvolvimento)

Para cada PDF gera dados_privados\\cache\\mascarado\\documento_N.txt com cada linha de texto
(e cada comentário do PDF) na ordem da folha, com posição em mm e tamanho da fonte.

Regras do mascaramento:
- termos técnicos (ÁREA, TERRENO, RECUO, PAVIMENTO, m²...) e palavras de até 2 letras: como estão;
- medidas (5,00 · 450,00 · 1.234,56 · 12.50 · 60% · +3,02) e números de até 3 dígitos: como estão;
- qualquer outra palavra vira só o formato: "Silva" → "Xxxxx";
- identificadores (matrícula, CPF, RRT, CAU, datas, telefones): dígitos viram 9.

Os nomes dos arquivos não aparecem na saída (ficam só em indice.txt, na pasta local).
CONFIRA a saída antes de compartilhá-la.
"""

from __future__ import annotations

import math
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = RAIZ / "dados_privados" / "desenvolvimento"
PASTA_SAIDA = RAIZ / "dados_privados" / "cache" / "mascarado"
MM = 25.4 / 72

VOCABULARIO = set("""
area areas terreno lote lotes quadra recuo recuos frontal frente fundos fundo lateral laterais
esquerdo esquerda direito direita testada testadas profundidade divisa divisas afastamento
afastamentos minimo minima maximo maxima taxa taxas ocupacao coeficiente aproveitamento
permeavel permeaveis permeabilidade indice indices construida construidas construido total
totais parcial computavel computaveis nao projecao edificacao edificada coberta cobertura
pavimento pavimentos pav terreo superior inferior subsolo mezanino planta plantas baixa situacao
localizacao implantacao corte cortes fachada fachadas elevacao vista detalhe detalhes escala
escalas indicada sem prancha pranchas folha folhas revisao revisoes rev data emissao inicial
projeto projetos arquitetonico arquitetonica executivo legal aprovacao autor autoria responsavel
tecnico tecnica proprietario proprietaria proprietarios interessado requerente contratante
matricula cartorio registro oficio imoveis imovel condominio residencial horizontal endereco
logradouro rua avenida alameda travessa estrada municipio cidade estado bairro cep obra local
conteudo desenho desenhos assinatura assinaturas cau crea rrt art reg prof quadro areas
descricao uso residencia unifamiliar casa habitacao sala estar jantar cozinha copa servico
lavanderia lavabo banho banheiro wc suite dormitorio dormitorios quarto quartos closet
circulacao hall escada garagem abrigo varanda terraco sacada gourmet churrasqueira piscina
deck jardim quintal deposito despensa escritorio home office gabinete area de do da dos das
em no na nos nas para por com ao aos e ou a o as os um uma porta portas portao janela janelas
basculante correr giro esquadria esquadrias vidro aluminio madeira peitoril altura alturas
largura comprimento espessura nivel niveis cota cotas pe direito laje lajes viga vigas pilar
pilares parede paredes alvenaria muro muros fechamento grade gradil calcada passeio meio fio
rebaixo acesso acessos veiculos pedestres entrada saida telha telhas telhado ceramica ceramico
fibrocimento metalica inclinacao caimento cumeeira calha calhas rufo beiral platibanda
reservatorio caixa agua litros piso pisos revestimento pintura acrilica textura grama gramado
paisagismo drenagem norte sul leste oeste magnetico verdadeiro rosa ventos sobe desce degrau
degraus patamar observacao observacoes nota notas legenda conforme ver existente demolir
construir reformar ampliacao reforma regularizacao memorial descritivo especificacao
especificacoes tabela quantidade quant und un unid zona zoneamento uso lei decreto artigo art
paragrafo inciso anexo codigo obras posturas parametros parametro urbanistico urbanisticos
cpf cnpj rg nº n no numero tel telefone email site www
m m2 m² m³ cm mm km l kg ha esq dir
""".split())

UNIDADES = {"m²", "m2", "m³", "m", "cm", "mm", "%", "l", "un"}

_MEDIDA = re.compile(
    r"^[+-]?(?:\d{1,3}(?:\.\d{3})+,\d+|\d+[.,]\d{1,2}|\d{1,3})(?:\s*(?:m²|m2|m³|m|cm|mm|%))?$",
    re.IGNORECASE,
)
_ORDINAL = re.compile(r"^\d{1,2}[ºª°]$")
_PONTUACAO_INICIAL = "([{\"'«“"
_PONTUACAO_FINAL = ".,;:)]}\"'»”!?"


def _normalizar(palavra: str) -> str:
    decomposto = unicodedata.normalize("NFD", palavra.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _formato(texto: str) -> str:
    return "".join("X" if c.isupper() else "x" if c.isalpha() else "9" if c.isdigit() else c
                   for c in texto)


def _mascarar_nucleo(nucleo: str) -> str:
    if not nucleo:
        return nucleo
    if "=" in nucleo:  # ex.: i=2%, A=12,50
        return "=".join(_mascarar_nucleo(parte) for parte in nucleo.split("="))
    if _MEDIDA.match(nucleo) or nucleo.lower() in UNIDADES or _ORDINAL.match(nucleo):
        return nucleo
    if nucleo.isalpha():
        if len(nucleo) <= 2 or _normalizar(nucleo) in VOCABULARIO:
            return nucleo
        return _formato(nucleo)
    # Palavra técnica com unidade colada ou barra (ex.: "Lote/Quadra"): avaliar por partes
    partes = re.split(r"([/\-'’])", nucleo)
    if len(partes) > 1 and all(p.isalpha() or p in "/-'’" or not p for p in partes):
        return "".join(_mascarar_nucleo(p) if p not in "/-'’" else p for p in partes)
    return _formato(nucleo)


def mascarar_token(token: str) -> str:
    inicio = len(token) - len(token.lstrip(_PONTUACAO_INICIAL))
    fim = len(token.rstrip(_PONTUACAO_FINAL))
    if fim <= inicio:
        return token
    return token[:inicio] + _mascarar_nucleo(token[inicio:fim]) + token[fim:]


def mascarar_texto(texto: str) -> str:
    return "".join(parte if parte.isspace() or not parte else mascarar_token(parte)
                   for parte in re.split(r"(\s+)", texto))


def _linhas_da_pagina(pagina: pymupdf.Page) -> list[tuple[float, float, str]]:
    linhas = []
    for bloco in pagina.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            texto = "".join(span["text"] for span in linha["spans"]).strip()
            if not texto:
                continue
            x0, y0, _x1, _y1 = linha["bbox"]
            tamanho = max(span["size"] for span in linha["spans"])
            dx, dy = linha["dir"]
            rotacao = "" if (dx, dy) == (1.0, 0.0) else f", girado {_angulo(dx, dy)}°"
            descricao = (f"[x={x0 * MM:5.0f} y={y0 * MM:5.0f} mm, {tamanho:4.1f} pt{rotacao}] "
                         f"{mascarar_texto(texto)}")
            linhas.append((round(y0 * MM), x0 * MM, descricao))
    return sorted(linhas)


def _angulo(dx: float, dy: float) -> int:
    return round(math.degrees(math.atan2(-dy, dx)))


def mascarar_documento(caminho: Path) -> str:
    saida = []
    with pymupdf.open(caminho) as documento:
        saida.append(f"# documento — {len(documento)} página(s)")
        for numero, pagina in enumerate(documento, start=1):
            saida.append(f"\n## página {numero} — {pagina.rect.width * MM:.0f}×"
                         f"{pagina.rect.height * MM:.0f} mm")
            linhas = _linhas_da_pagina(pagina)
            saida.append(f"### {len(linhas)} linha(s) de texto")
            saida.extend(descricao for _, _, descricao in linhas)
            comentarios = [a for a in pagina.annots() if (a.info.get("content") or "").strip()]
            saida.append(f"### {len(comentarios)} comentário(s) com texto")
            for anotacao in comentarios:
                r = anotacao.rect
                saida.append(f"[comentário {anotacao.type[1]} x={r.x0 * MM:5.0f} "
                             f"y={r.y0 * MM:5.0f} mm] "
                             f"{mascarar_texto(anotacao.info['content'].strip())}")
    return "\n".join(saida) + "\n"


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
        destino = PASTA_SAIDA / f"documento_{numero}.txt"
        try:
            texto = mascarar_documento(caminho)
        except Exception as erro:  # arquivo corrompido, protegido por senha etc.
            print(f"documento {numero}: não foi possível ler ({type(erro).__name__})")
            continue
        destino.write_text(texto, encoding="utf-8")
        indice.append(f"documento_{numero}.txt = {caminho}")
        print(f"documento {numero}: {texto.count(chr(10))} linhas → {destino.relative_to(RAIZ)}")
    (PASTA_SAIDA / "indice.txt").write_text("\n".join(indice) + "\n", encoding="utf-8")
    print("\nConfira os arquivos antes de compartilhar. indice.txt (com os nomes reais dos "
          "arquivos) é só para você.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
