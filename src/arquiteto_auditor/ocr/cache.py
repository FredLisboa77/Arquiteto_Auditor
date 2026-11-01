"""Cache do OCR em disco: o OCR é lento (segundos por página); a 2ª leitura deve ser imediata.

Uma pasta por documento (o hash do PDF), um arquivo JSON por imagem lida. A chave inclui a
versão do pré-processamento e o idioma: mudou o OCR, o cache antigo deixa de valer.
O cache contém texto de documentos: fica em dados_privados/ (nunca vai para o Git).
"""

from __future__ import annotations

import json
from pathlib import Path

from arquiteto_auditor.ocr.tesseract import VERSAO, PalavraOCR


class CacheOCR:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)

    def _arquivo(self, hash_documento: str, nome: str, idioma: str) -> Path:
        return self.pasta / hash_documento / f"{nome}_v{VERSAO}_{idioma}.json"

    def ler(self, hash_documento: str, nome: str, idioma: str) -> list[PalavraOCR] | None:
        arquivo = self._arquivo(hash_documento, nome, idioma)
        if not arquivo.exists():
            return None
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return [PalavraOCR(p["texto"], tuple(p["bbox"]), p["confianca"], p["bloco"], p["linha"])
                for p in dados]

    def gravar(self, hash_documento: str, nome: str, idioma: str,
               palavras: list[PalavraOCR]) -> None:
        arquivo = self._arquivo(hash_documento, nome, idioma)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        dados = [{"texto": p.texto, "bbox": list(p.bbox), "confianca": p.confianca,
                  "bloco": p.bloco, "linha": p.linha} for p in palavras]
        arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
