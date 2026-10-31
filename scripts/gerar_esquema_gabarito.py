"""Gera docs/esquemas/gabarito.schema.json a partir do modelo Gabarito.

Rode sempre que mudar o formato do gabarito:
    .venv\\Scripts\\python scripts\\gerar_esquema_gabarito.py
"""

import json
from pathlib import Path

from arquiteto_auditor.avaliacao.gabarito import esquema_json

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "esquemas" / "gabarito.schema.json"

DESTINO.parent.mkdir(parents=True, exist_ok=True)
conteudo = json.dumps(esquema_json(), ensure_ascii=False, indent=2) + "\n"
DESTINO.write_text(conteudo, encoding="utf-8")
print(f"Esquema gravado em {DESTINO}")
