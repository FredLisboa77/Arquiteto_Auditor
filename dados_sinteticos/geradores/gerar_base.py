"""Gera a base sintética de pranchas em dados_sinteticos/projetos/.

Uso:
    .venv\\Scripts\\python -m dados_sinteticos.geradores.gerar_base             (todos)
    .venv\\Scripts\\python -m dados_sinteticos.geradores.gerar_base sint-003    (um só)

Cada conjunto vira uma pasta com as pranchas (assinadas), gabarito.json e especificacao.json.
As assinaturas usam certificados gerados na hora: regerar um conjunto muda os bytes dos PDFs,
mas não o conteúdo. Regere só quando a especificação ou o desenho mudarem.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dados_sinteticos.geradores.assinatura import Assinante, assinar_pdf
from dados_sinteticos.geradores.especificacao import (
    Projeto,
    aplicar_erros,
    como_dicionario,
    gerar_gabarito,
    gerar_projeto_base,
)
from dados_sinteticos.geradores.pranchas import gerar_pdfs

PASTA_PROJETOS = Path(__file__).resolve().parent.parent / "projetos"
ESQUEMA_RELATIVO = "../../../docs/esquemas/gabarito.schema.json"


@dataclass(frozen=True)
class DefinicaoConjunto:
    conjunto: str
    semente: int
    erros: tuple[str, ...] = ()
    variacao: dict = field(default_factory=dict)  # sobrepõe a variação sorteada
    reservado: bool = False  # reservado para avaliação (não usar ao desenvolver regras)


CONJUNTOS: tuple[DefinicaoConjunto, ...] = (
    DefinicaoConjunto(
        "sint-001", 101, (),
        {"estilo_carimbo": 0, "estilo_quadro": 0, "formato": "A1", "arquivo_unico": True}),
    DefinicaoConjunto(
        "sint-002", 102, ("area_terreno_divergente", "matricula_divergente"),
        {"estilo_carimbo": 1, "estilo_quadro": 1, "formato": "A2", "decimal_ponto": True}),
    DefinicaoConjunto(
        "sint-003", 103, ("cota_omitida:recuo_fundos", "cota_omitida:altura_total", "sem_norte"),
        {"estilo_carimbo": 2, "estilo_quadro": 2, "formato": "A3", "cotas_rotuladas": False}),
    DefinicaoConjunto(
        "sint-004", 104, ("sem_assinatura_proprietario", "sem_proprietario", "muro_alto"),
        {"estilo_carimbo": 3, "estilo_quadro": 3, "formato": "A1", "arquivo_unico": False}),
    DefinicaoConjunto(
        "sint-005", 105, ("assinatura_alterada", "soma_areas_errada", "revisao_divergente"),
        {"estilo_carimbo": 0, "estilo_quadro": 2, "formato": "A2", "caixa_alta": False}),
    DefinicaoConjunto(
        "sint-006", 106, ("to_excedida", "recuo_frontal_insuficiente", "altura_excedida"),
        {"estilo_carimbo": 1, "estilo_quadro": 3, "formato": "A3"}),
    DefinicaoConjunto(
        "sint-007", 107,
        ("area_terreno_divergente", "cota_omitida:testada", "sem_norte", "sem_assinatura_autor"),
        {"estilo_carimbo": 2, "estilo_quadro": 0, "formato": "A2"}, reservado=True),
    DefinicaoConjunto(
        "sint-008", 108, ("to_declarada_errada", "matricula_divergente", "muro_alto"),
        {"estilo_carimbo": 3, "estilo_quadro": 1, "formato": "A3", "decimal_ponto": True},
        reservado=True),
)


def montar_projeto(definicao: DefinicaoConjunto) -> Projeto:
    projeto = aplicar_erros(gerar_projeto_base(definicao.semente), list(definicao.erros))
    projeto.variacao = dataclasses.replace(projeto.variacao, **definicao.variacao)
    return projeto


def gerar_conjunto(definicao: DefinicaoConjunto, destino: Path = PASTA_PROJETOS) -> Path:
    projeto = montar_projeto(definicao)
    pasta = Path(destino) / definicao.conjunto
    pasta.mkdir(parents=True, exist_ok=True)
    for antigo in pasta.glob("*.pdf"):
        antigo.unlink()

    a = projeto.apresentacao
    autor = Assinante.criar(projeto.identificacao.autor) if a.assinatura_autor else None
    proprietario = (Assinante.criar(projeto.identificacao.proprietario)
                    if a.assinatura_proprietario else None)
    for nome, conteudo in gerar_pdfs(projeto):
        assinado = assinar_pdf(conteudo, autor, proprietario, alterar_depois=a.assinatura_alterada)
        (pasta / nome).write_bytes(assinado)

    gabarito = gerar_gabarito(projeto, definicao.conjunto)
    gabarito.reservado_avaliacao = definicao.reservado
    dados = {"$schema": ESQUEMA_RELATIVO} | gabarito.model_dump(
        mode="json", exclude_none=True, exclude={"esquema"})
    (pasta / "gabarito.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (pasta / "especificacao.json").write_text(
        json.dumps(como_dicionario(projeto), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return pasta


def main(argumentos: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    escolhidos = [d for d in CONJUNTOS if not argumentos or d.conjunto in argumentos]
    if not escolhidos:
        print(f"Nenhum conjunto encontrado: {argumentos}")
        return 1
    falhas = 0
    for definicao in escolhidos:
        try:
            pasta = gerar_conjunto(definicao)
        except PermissionError as erro:
            falhas += 1
            print(f"{definicao.conjunto}: NÃO GERADO — o arquivo {Path(erro.filename).name} está "
                  "aberto em outro programa (feche o leitor de PDF e rode de novo).")
            continue
        erros = ", ".join(definicao.erros) or "nenhum (conjunto limpo)"
        reservado = "  [RESERVADO PARA AVALIAÇÃO]" if definicao.reservado else ""
        print(f"{definicao.conjunto}: {len(list(pasta.glob('*.pdf')))} PDF(s) — erros: "
              f"{erros}{reservado}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
