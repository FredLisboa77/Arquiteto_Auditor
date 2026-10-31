"""Gera a base sintética em dados_sinteticos/projetos/ (pranchas, matrícula e escritura).

Uso:
    .venv\\Scripts\\python -m dados_sinteticos.geradores.gerar_base             (todos)
    .venv\\Scripts\\python -m dados_sinteticos.geradores.gerar_base sint-003    (um só)

Cada conjunto vira uma pasta com as pranchas (assinadas), a matrícula e a escritura
(escaneadas), gabarito.json, especificacao.json e verdade_ocr.json (texto de cada página
escaneada, para medir o OCR).
As assinaturas usam certificados gerados na hora: regerar um conjunto muda os bytes dos PDFs,
mas não o conteúdo. Regere só quando a especificação ou o desenho mudarem.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from arquiteto_auditor.avaliacao.gabarito import Gabarito
from dados_sinteticos.geradores.assinatura import Assinante, assinar_pdf
from dados_sinteticos.geradores.escritura import Escritura, gerar_escritura_escaneada
from dados_sinteticos.geradores.especificacao import (
    Projeto,
    aplicar_erros,
    como_dicionario,
    gerar_gabarito,
    gerar_projeto_base,
)
from dados_sinteticos.geradores.memorial import (
    gerar_memorial,
    gerar_memorial_escaneado,
    gerar_memorial_pdf,
)
from dados_sinteticos.geradores.pranchas import gerar_pdfs
from dados_sinteticos.geradores.registro import Matricula, gerar_matricula_escaneada

PASTA_PROJETOS = Path(__file__).resolve().parent.parent / "projetos"
ESQUEMA_RELATIVO = "../../../docs/esquemas/gabarito.schema.json"


@dataclass(frozen=True)
class DefinicaoConjunto:
    conjunto: str
    semente: int
    erros: tuple[str, ...] = ()
    variacao: dict = field(default_factory=dict)  # sobrepõe a variação sorteada
    reservado: bool = False  # reservado para avaliação (não usar ao desenvolver regras)
    matricula: tuple[str, str] = ("certidao", "boa")  # (estilo, qualidade do escaneamento)
    escritura: str = "boa"  # qualidade do escaneamento
    memorial: str = "texto"  # "texto" (digitado e assinado digitalmente) ou qualidade do escaneado


CONJUNTOS: tuple[DefinicaoConjunto, ...] = (
    DefinicaoConjunto(
        "sint-001", 101, (),
        {"estilo_carimbo": 0, "estilo_quadro": 0, "formato": "A1", "arquivo_unico": True}),
    DefinicaoConjunto(
        "sint-002", 102, ("area_terreno_divergente", "matricula_divergente"),
        {"estilo_carimbo": 1, "estilo_quadro": 1, "formato": "A2", "decimal_ponto": True},
        matricula=("ficha", "media")),
    DefinicaoConjunto(
        "sint-003", 103, ("cota_omitida:recuo_fundos", "cota_omitida:altura_total", "sem_norte"),
        {"estilo_carimbo": 2, "estilo_quadro": 2, "formato": "A3", "cotas_rotuladas": False},
        matricula=("certidao", "media"), escritura="media", memorial="media"),
    DefinicaoConjunto(
        "sint-004", 104, ("sem_assinatura_proprietario", "sem_proprietario", "muro_alto"),
        {"estilo_carimbo": 3, "estilo_quadro": 3, "formato": "A1", "arquivo_unico": False},
        escritura="ruim"),
    DefinicaoConjunto(
        "sint-005", 105, ("assinatura_alterada", "soma_areas_errada", "revisao_divergente"),
        {"estilo_carimbo": 0, "estilo_quadro": 2, "formato": "A2", "caixa_alta": False},
        matricula=("ficha", "ruim")),
    DefinicaoConjunto(
        "sint-006", 106, ("to_excedida", "recuo_frontal_insuficiente", "altura_excedida"),
        {"estilo_carimbo": 1, "estilo_quadro": 3, "formato": "A3"},
        escritura="media", memorial="boa"),
    DefinicaoConjunto(
        "sint-007", 107,
        ("area_terreno_divergente", "cota_omitida:testada", "sem_norte", "sem_assinatura_autor"),
        {"estilo_carimbo": 2, "estilo_quadro": 0, "formato": "A2"}, reservado=True,
        matricula=("certidao", "media")),
    DefinicaoConjunto(
        "sint-008", 108, ("to_declarada_errada", "matricula_divergente", "muro_alto"),
        {"estilo_carimbo": 3, "estilo_quadro": 1, "formato": "A3", "decimal_ponto": True},
        reservado=True, matricula=("ficha", "boa"), escritura="media", memorial="ruim"),
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

    estilo, qualidade = definicao.matricula
    matricula, doc_matricula = gerar_matricula_escaneada(projeto, qualidade, estilo=estilo)
    escritura, doc_escritura = gerar_escritura_escaneada(projeto, definicao.escritura,
                                                         matricula)
    (pasta / "matricula.pdf").write_bytes(doc_matricula.pdf)
    (pasta / "escritura.pdf").write_bytes(doc_escritura.pdf)
    verdade_ocr = {
        "descricao": "Texto impresso de cada página escaneada (sem carimbos, selos e "
                     "assinaturas), para medir o OCR. Página em branco = \"\".",
        "matricula.pdf": doc_matricula.texto_por_pagina,
        "escritura.pdf": doc_escritura.texto_por_pagina,
    }

    memorial = gerar_memorial(projeto)
    if definicao.memorial == "texto":  # digitado: assinado como as pranchas (sem alteração)
        (pasta / "memorial.pdf").write_bytes(
            assinar_pdf(gerar_memorial_pdf(memorial), autor, proprietario))
    else:  # impresso, assinado à caneta e escaneado
        doc_memorial = gerar_memorial_escaneado(memorial, definicao.memorial,
                                                projeto.semente * 67)
        (pasta / "memorial.pdf").write_bytes(doc_memorial.pdf)
        verdade_ocr["memorial.pdf"] = doc_memorial.texto_por_pagina
    _gravar_json(pasta / "verdade_ocr.json", verdade_ocr)

    gabarito = _completar_gabarito(gerar_gabarito(projeto, definicao.conjunto), matricula,
                                   escritura)
    gabarito.reservado_avaliacao = definicao.reservado
    _gravar_json(pasta / "gabarito.json", {"$schema": ESQUEMA_RELATIVO} | gabarito.model_dump(
        mode="json", exclude_none=True, exclude={"esquema"}))
    especificacao = como_dicionario(projeto)
    especificacao["documentos_registrais"] = _resumo_registral(definicao, matricula, escritura)
    _gravar_json(pasta / "especificacao.json", especificacao)
    return pasta


def _gravar_json(caminho: Path, dados: dict) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _completar_gabarito(gabarito: Gabarito, matricula: Matricula,
                        escritura: Escritura) -> Gabarito:
    """Acrescenta o que a matrícula e a escritura mostram (a matrícula é a verdade atual)."""
    dados = gabarito.model_dump(by_alias=True)
    valores = dados["valores_esperados"]
    valores["TERRENO_AREA"]["escritura"] = escritura.venda.area
    valores["ID_PROPRIETARIO"] = {"matricula": matricula.proprietario_atual,
                                  "escritura": escritura.venda.comprador.nome}
    return Gabarito.model_validate(dados)


def _resumo_registral(definicao: DefinicaoConjunto, matricula: Matricula,
                      escritura: Escritura) -> dict:
    venda = escritura.venda
    return {
        "matricula": {
            "estilo": definicao.matricula[0], "qualidade": definicao.matricula[1],
            "area_atual": matricula.area_atual,
            "proprietario_atual": matricula.proprietario_atual,
            "onus_ativos": matricula.onus_ativos,
            "atos": [f"{a.codigo} {a.titulo} ({a.data:%d/%m/%Y})" for a in matricula.atos],
        },
        "escritura": {
            "qualidade": definicao.escritura, "registrada_em": venda.codigo_ato,
            "data": f"{venda.data_escritura:%d/%m/%Y}", "valor": venda.valor,
            "area_descrita": venda.area,
            "area_diferente_da_atual": venda.area != matricula.area_atual,
        },
    }


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
