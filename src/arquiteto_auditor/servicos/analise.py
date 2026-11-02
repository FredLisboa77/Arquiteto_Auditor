"""Análise completa de um projeto: lê todos os documentos, aplica a hierarquia dos
parâmetros e roda o motor de verificação. É o que a interface (Fase 10) vai chamar.

Ordem: pranchas → memorial → matrícula → escritura → lei (zona pelo condomínio das
pranchas; faixa de área pelo terreno da matrícula) → norma do condomínio → hierarquia →
completude → motor. Documento que não foi enviado simplesmente não entra: os itens que
dependem dele ficam "não foi possível verificar".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from arquiteto_auditor.dominio.constatacao import Constatacao
from arquiteto_auditor.dominio.documento import DocumentoLido
from arquiteto_auditor.dominio.modelos import ItemVerificacao, OrigemValor, ValorExtraido
from arquiteto_auditor.dominio.parametros import ParametroAdotado
from arquiteto_auditor.extracao.memorial import ler_memorial
from arquiteto_auditor.extracao.parametros.extrator import ParametrosDoDocumento, ler_parametros
from arquiteto_auditor.extracao.parametros.hierarquia import adotar
from arquiteto_auditor.extracao.pranchas import extrair_pranchas
from arquiteto_auditor.extracao.pranchas.completude import verificar_completude
from arquiteto_auditor.extracao.registro import ler_escritura, ler_matricula
from arquiteto_auditor.extracao.texto_corrido import TextoCorrido
from arquiteto_auditor.ingestao.leitor import LeitorPDF
from arquiteto_auditor.llm.cliente import ClienteLLM
from arquiteto_auditor.verificacao.motor import Fatos, verificar


@dataclass
class DocumentosDoProjeto:
    pranchas: list[Path] = field(default_factory=list)
    memorial: Path | None = None
    matricula: Path | None = None
    escritura: Path | None = None
    lei_municipal: Path | None = None
    norma_condominio: Path | None = None


@dataclass
class ResultadoDaAnalise:
    itens: list[ItemVerificacao]
    fatos: Fatos
    lei: ParametrosDoDocumento | None = None
    norma: ParametrosDoDocumento | None = None
    pendencias: list[str] = field(default_factory=list)  # atos não compreendidos etc.

    @property
    def parametros(self) -> dict[str, ParametroAdotado]:
        return self.fatos.parametros

    @property
    def constatacoes(self) -> list[Constatacao]:
        return self.fatos.constatacoes


def _numero_da_matricula(documento: DocumentoLido, numero: str | None) -> ValorExtraido | None:
    """O número lido, com a evidência de onde ele está escrito no documento."""
    if not numero:
        return None
    corrido = TextoCorrido(documento)
    posicao = corrido.texto.find(numero)
    if posicao < 0:
        return None
    evidencia = corrido.evidencia(posicao, posicao + len(numero), documento.arquivo)
    return ValorExtraido(campo="MATRICULA", valor=numero,
                         origem=OrigemValor.OCR if evidencia.confianca_ocr is not None
                         else OrigemValor.VETORIAL, confianca=0.9, evidencias=[evidencia])


def analisar(documentos: DocumentosDoProjeto, *, leitor: LeitorPDF | None = None,
             cliente: ClienteLLM | None = None,
             zona_informada: str | None = None) -> ResultadoDaAnalise:
    """Análise completa (ver o início do módulo). cliente=None → sem LLM."""
    leitor = leitor or LeitorPDF()
    fatos = Fatos()
    pendencias: list[str] = []

    pranchas = [leitor.ler(caminho) for caminho in documentos.pranchas]
    if pranchas:
        fatos.pranchas = extrair_pranchas(pranchas)
        fatos.constatacoes = verificar_completude(pranchas, fatos.pranchas)
        fatos.arquivos_pranchas = [p.arquivo for p in pranchas]
    if documentos.memorial:
        fatos.memorial = ler_memorial(leitor.ler(documentos.memorial))
    if documentos.matricula:
        lido = leitor.ler(documentos.matricula)
        matricula = ler_matricula(lido)
        fatos.matricula = dict(matricula.estado_atual)
        if numero := _numero_da_matricula(lido, matricula.numero):
            fatos.matricula["MATRICULA"] = numero
        pendencias += matricula.pendencias
    if documentos.escritura:
        escritura = ler_escritura(leitor.ler(documentos.escritura))
        fatos.escritura = dict(escritura.campos)
        pendencias += escritura.pendencias

    condominio = fatos.pranchas.get("CONDOMINIO") or fatos.memorial.get("CONDOMINIO")
    area = fatos.area_do_terreno()
    lei = norma = None
    if documentos.lei_municipal:
        lei = ler_parametros(documentos.lei_municipal, leitor.ler(documentos.lei_municipal),
                             "prefeitura", cliente=cliente,
                             nome_condominio=str(condominio.valor) if condominio else None,
                             zona_informada=zona_informada,
                             area_lote=float(area.valor) if area else None)
    if documentos.norma_condominio:
        norma = ler_parametros(documentos.norma_condominio,
                               leitor.ler(documentos.norma_condominio), "condominio",
                               cliente=cliente)
    fatos.parametros = adotar(lei, norma)
    return ResultadoDaAnalise(itens=verificar(fatos), fatos=fatos, lei=lei, norma=norma,
                              pendencias=pendencias)
