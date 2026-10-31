"""Verificação anti-vazamento: impede que dados pessoais entrem no repositório público.

Roda automaticamente antes de cada `git commit` (via pre-commit) e recebe a lista de
arquivos que estão sendo commitados. Bloqueia o commit se encontrar:

1. qualquer arquivo dentro de `dados_privados/` (exceto o LEIAME.md);
2. documentos ou imagens (PDF, DOCX, PNG...) fora das pastas de dados sintéticos;
3. bancos de dados locais (.db, .sqlite);
4. arquivos maiores que o limite (documentos escaneados costumam ser grandes);
5. CPF com dígitos verificadores VÁLIDOS em arquivos de texto. Os dados sintéticos
   usam de propósito CPFs com dígitos inválidos, então um CPF válido indica dado real.

Uso manual:  python scripts/verificar_vazamento.py ARQUIVO [ARQUIVO ...]
             python scripts/verificar_vazamento.py --todos   (verifica tudo que o Git rastreia)
Usa apenas a biblioteca padrão do Python, para funcionar com qualquer interpretador.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

LIMITE_BYTES = 5 * 1024 * 1024

PASTA_PRIVADA = "dados_privados/"
EXCECOES_PRIVADAS = {"dados_privados/LEIAME.md"}

EXTENSOES_DOCUMENTO = {
    ".pdf", ".docx", ".doc", ".odt", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".bmp", ".dwg", ".dxf", ".zip", ".7z", ".rar",
}
PASTAS_DOCUMENTOS_PERMITIDOS = ("dados_sinteticos/", "tests/fixtures/", "docs/img/")

EXTENSOES_BANCO = {".db", ".sqlite", ".sqlite3", ".db-journal"}

EXTENSOES_TEXTO = {
    ".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".csv", ".html", ".cfg", ".ini",
}

PADRAO_CPF = re.compile(r"(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")


def cpf_valido(digitos: str) -> bool:
    """Confere os dois dígitos verificadores de um CPF (11 dígitos, sem pontuação)."""
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    numeros = [int(d) for d in digitos]
    for posicao in (9, 10):
        soma = sum(numeros[i] * (posicao + 1 - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != numeros[posicao]:
            return False
    return True


def problemas_do_caminho(caminho: str) -> list[str]:
    """Regras que dependem só do nome/pasta do arquivo."""
    caminho = PurePosixPath(caminho.replace("\\", "/")).as_posix()
    sufixo = PurePosixPath(caminho).suffix.lower()
    problemas = []

    if caminho.startswith(PASTA_PRIVADA) and caminho not in EXCECOES_PRIVADAS:
        problemas.append("está em dados_privados/ (documentos reais nunca vão para o Git)")
    if sufixo in EXTENSOES_DOCUMENTO and not caminho.startswith(PASTAS_DOCUMENTOS_PERMITIDOS):
        problemas.append(
            f"documento/imagem '{sufixo}' fora das pastas permitidas "
            f"({', '.join(PASTAS_DOCUMENTOS_PERMITIDOS)})"
        )
    if sufixo in EXTENSOES_BANCO:
        problemas.append("banco de dados local (histórico com dados pessoais)")
    return problemas


def problemas_do_conteudo(caminho: Path) -> list[str]:
    """Regras que leem o arquivo: tamanho e CPF válido em arquivos de texto."""
    problemas = []
    if not caminho.is_file():
        return problemas
    if caminho.stat().st_size > LIMITE_BYTES:
        problemas.append(f"arquivo maior que {LIMITE_BYTES // (1024 * 1024)} MB")
    if caminho.suffix.lower() in EXTENSOES_TEXTO:
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        for numero in PADRAO_CPF.finditer(texto):
            if cpf_valido("".join(numero.groups())):
                problemas.append(
                    "contém um CPF com dígitos verificadores válidos (possível dado real); "
                    "dados sintéticos devem usar CPF inválido"
                )
                break
    return problemas


def verificar(caminhos: list[str], raiz: Path) -> dict[str, list[str]]:
    resultado = {}
    for caminho in caminhos:
        problemas = problemas_do_caminho(caminho) + problemas_do_conteudo(raiz / caminho)
        if problemas:
            resultado[caminho] = problemas
    return resultado


def arquivos_rastreados(raiz: Path) -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files"], cwd=raiz, capture_output=True, text=True, check=True
    )
    return [linha for linha in saida.stdout.splitlines() if linha]


def main(argumentos: list[str]) -> int:
    # O console do Windows pode usar cp1252, que não tem "✗" nem alguns acentos.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raiz = Path(__file__).resolve().parent.parent
    caminhos = arquivos_rastreados(raiz) if argumentos == ["--todos"] else argumentos
    resultado = verificar(caminhos, raiz)
    if not resultado:
        print(f"Verificação anti-vazamento: OK ({len(caminhos)} arquivo(s)).")
        return 0
    print("COMMIT BLOQUEADO — possível vazamento de dados pessoais:\n")
    for caminho, problemas in resultado.items():
        for problema in problemas:
            print(f"  ✗ {caminho}: {problema}")
    print(
        "\nRemova esses arquivos do commit com:  git restore --staged <arquivo>\n"
        "Nunca use --no-verify para contornar esta verificação (ver CLAUDE.md)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
