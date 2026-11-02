"""Valor adotado de cada parâmetro: a PREFEITURA prevalece sobre o CONDOMÍNIO.

Regra definida pelo usuário em 30/10/2026 (CLAUDE.md §3, princípio 7):
- definido só por um dos dois → usa esse. Mas se o parâmetro costuma vir da lei (recuos,
  TO, CA...) e só foi achado no condomínio, ele fica pendente: "não achei na lei" não é o
  mesmo que "a lei não define" (a leitura da lei pode ter falhado);
- definido pelos dois com o mesmo valor → usa o da prefeitura (e registra que coincidem);
- definido pelos dois com valores diferentes → adota o da prefeitura e registra o valor do
  condomínio, com o trecho e a página, como observação no item.
Nenhum parâmetro é inventado: o que nenhum documento define fica de fora (o motor de
verificação mostra "não foi possível verificar").
"""

from __future__ import annotations

import math

from arquiteto_auditor.dominio.modelos import StatusConfirmacao, ValorExtraido
from arquiteto_auditor.dominio.parametros import ParametroAdotado
from arquiteto_auditor.extracao.parametros.definicoes import POR_CHAVE
from arquiteto_auditor.extracao.parametros.extrator import ParametrosDoDocumento


def _numero(valor: float | str) -> str:
    texto = f"{float(valor):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _onde(valor: ValorExtraido) -> str:
    evidencia = valor.evidencias[0]
    return f"{evidencia.documento}, pág. {evidencia.pagina}: “{evidencia.trecho}”"


def adotar(prefeitura: ParametrosDoDocumento | None,
           condominio: ParametrosDoDocumento | None) -> dict[str, ParametroAdotado]:
    """Um parâmetro adotado por chave do catálogo (ver o início do módulo)."""
    da_prefeitura = prefeitura.valores if prefeitura else {}
    do_condominio = condominio.valores if condominio else {}
    adotados = {}
    for chave in sorted(set(da_prefeitura) | set(do_condominio)):
        p, c = da_prefeitura.get(chave), do_condominio.get(chave)
        if p is None:
            definicao = POR_CHAVE.get(chave)
            if definicao is None or definicao.tipico_da_lei:
                aviso = ("Encontrado só na norma do condomínio. Confirme se a lei municipal "
                         "define este parâmetro: se definir, vale o da prefeitura.")
                c = c.model_copy(update={"status": StatusConfirmacao.PENDENTE})
            else:
                aviso = "Definido só pela norma do condomínio."
            adotados[chave] = ParametroAdotado(chave, c, "condominio", observacao=aviso)
            continue
        observacao = None
        if c is not None:
            if math.isclose(float(p.valor), float(c.valor), abs_tol=1e-6):
                observacao = "A norma do condomínio define o mesmo valor."
            else:
                observacao = (f"A norma do condomínio define {_numero(c.valor)} "
                              f"({_onde(c)}); vale o da prefeitura, que prevalece.")
        adotados[chave] = ParametroAdotado(chave, p, "prefeitura", c, observacao)
    return adotados
