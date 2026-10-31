# 05 — Avaliação de qualidade

> Como saber se o software está **acertando**, sem depender de impressão. Usaremos duas bases: a **sintética** (no repositório, para desenvolvimento e testes automáticos) e o **gabarito real** (só na sua máquina, para a validação final).

---

## 1. Conceitos

| Termo | Significado |
|---|---|
| **Verdadeiro positivo (VP)** | Erro real que o software encontrou. |
| **Falso negativo (FN)** | Erro real que o software **deixou passar**. É o pior caso para você. |
| **Falso positivo (FP) / falso alarme** | Problema apontado que **não existe**. Irrita o autor e mina a confiança no relatório. |
| **Revocação** (*recall*) | VP ÷ (VP + FN): "dos erros que existem, quantos achamos?" |
| **Precisão** | VP ÷ (VP + FP): "do que apontamos, quanto era verdade?" |
| **CER** (*Character Error Rate*) | % de caracteres errados no OCR em relação ao texto verdadeiro. |
| **Gabarito** | Arquivo JSON com a resposta certa de cada conjunto de documentos. |

**Prioridade:** revocação alta (não deixar erro passar) **com** falsos alarmes baixos. Quando o sistema estiver em dúvida, a saída correta é **"pendente de confirmação"** ou **"não foi possível verificar"** — nunca um falso "atende".

---

## 2. Formato do gabarito (proposta — finalizado na Fase 2)

```json
{
  "conjunto": "sint-007",
  "versao_gabarito": 1,
  "rodada": "R00",
  "zona": "ZR-2",
  "valores_esperados": {
    "TERRENO_AREA":   {"prancha": 450.00, "memorial": 450.00, "matricula_atual": 452.30},
    "ID_MATRICULA":   {"prancha": "12.345", "matricula": "12.354"},
    "TO_MAX":         {"prefeitura": 60.0, "condominio": 50.0, "adotado": 50.0}
  },
  "itens_esperados": [
    {"chave": "TERRENO_AREA",  "status": "divergente",     "documentos": ["prancha", "matricula"]},
    {"chave": "ID_MATRICULA",  "status": "divergente",     "documentos": ["prancha", "matricula"]},
    {"chave": "TO_MAX",        "status": "nao_atende",     "valor_projeto": 52.1, "limite": 50.0},
    {"chave": "RECUO_FRONTAL", "status": "atende"},
    {"chave": "PARAM_CONFLITO_TO", "status": "sinalizacao"}
  ],
  "comparacao_rodada_anterior": [
    {"chave": "ID_MATRICULA", "resultado": "resolvido"},
    {"chave": "TO_MAX",       "resultado": "pendente"},
    {"chave": "RECUO_FUNDOS", "resultado": "novo"}
  ]
}
```

---

## 3. Métricas

### 3.1 Resultado final (o que importa para você)
| Métrica | Como calcula | Meta sintética (MVP) | Meta real |
|---|---|---|---|
| **Revocação de erros** | erros do gabarito encontrados ÷ total de erros | **≥ 95%** | **100% dos erros conhecidos** encontrados ou marcados para confirmação |
| **Falsos alarmes por conjunto** | itens "não atende/divergente" que não estão no gabarito | **≤ 1** em média; **0** no conjunto limpo | ≤ 2 |
| **Classificação correta dos itens** | status igual ao gabarito (4 classes) | ≥ 90% | registrar |
| **Falso "atende"** | item com erro real classificado como "atende" | **0** (crítico) | **0** |
| **Evidência rastreável** | itens com arquivo + página + trecho válidos | **100%** | 100% |

### 3.2 Versionamento
| Métrica | Meta |
|---|---|
| Comparação resolvido / pendente / novo correta | **100%** no projeto sintético R00→R01 |
| "Mesmo projeto" reconhecido (e não confundido com outro) | 100% nos sintéticos |
| Relatório emitido inalterado após nova rodada | 100% (teste automático compara *hash*) |

### 3.3 Por etapa (para descobrir **onde** está o problema)
| Etapa | Métrica | Meta sintética |
|---|---|---|
| Ingestão | vetorial × escaneado correto | 100% |
| Classificação | tipo de documento correto | ≥ 95% |
| OCR | CER em matrículas de qualidade boa / média / ruim | ≤ 1% / ≤ 3% / ≤ 8% |
| Extração pranchas | campos corretos (identificação / numéricos) | ≥ 95% / ≥ 90% |
| Registro | atos separados / estado atual correto | ≥ 95% / ≥ 90% |
| Parâmetros | parâmetros corretos / com citação verificada | ≥ 90% / 100% |
| Confiança | dos valores errados, quantos estavam marcados "pendente" | ≥ 80% |
| Confiança | dos valores marcados "pendente", quantos estavam certos (incômodo) | registrar; ideal ≤ 50% |
| Desempenho | tempo por projeto completo | ≤ 8 min (primeira vez) |

A métrica de **confiança** é chave: um sistema que erra mas **sabe que errou** (e te pede confirmação) é útil; um que erra com confiança alta é perigoso.

---

## 4. Como usar a base sintética

- **Testes automáticos** (`pytest`): rodam em cada mudança; usam conjuntos pequenos e rápidos.
- **Avaliação completa** (`scripts/avaliar.py`): roda todos os conjuntos, compara com os gabaritos e gera uma tabela com as métricas acima + lista de cada erro perdido e cada falso alarme (para depuração).
- **Regra anti-trapaça:** nenhuma regra de extração pode citar um valor ou texto específico de um conjunto sintético. Uma parte dos conjuntos (≥ 2) fica **reservada** e só é usada na avaliação, nunca durante o desenvolvimento das regras — para detectar regras "decoradas".
- Cada bug encontrado em documento real (sem expor o conteúdo) vira um **novo caso sintético** que o reproduz.

---

## 5. Como usar o gabarito real (sem expor dados)

1. Você cria `dados_privados/gabarito_real/gabarito.json` no mesmo formato (eu ajudo a montar a partir da sua descrição; você preenche os valores).
2. `scripts/avaliar.py --real` roda localmente e imprime **apenas números agregados** e chaves (ex.: "TERRENO_AREA: encontrado ✓", "RECUO_FUNDOS: não encontrado ✗") — sem valores, nomes ou trechos.
3. O resultado é registrado no histórico de avaliação (local) e resumido no relatório da fase.
4. Se você quiser que eu investigue um erro no documento real, **você decide** se me mostra o trecho; por padrão, eu trabalho só com as estatísticas.
5. Usar o gabarito real **só na Fase 13** (e no diagnóstico da Fase 3) para não ajustar o software "à mão" para aquele caso.

### 5.1 Erros conhecidos do conjunto real
Informado pelo usuário em 30/10/2026. Só tipo e quantidade, sem valores.

| Tipo de erro | Qtd. | Chave(s) que deve(m) apontar | Fase |
|---|---|---|---|
| Divergência de área entre documentos | 3 | `TERRENO_AREA`, `AREA_CONSTR_*` | 6, 7, 9 |
| Indefinição de cotas e dimensões apenas gráficas | 3 | `COTA_INDEFINIDA` | 6 |
| Pendência de assinaturas (omissão + validação técnica da assinatura digital) | 2 | `ASSINATURA_AUTOR`, `ASSINATURA_PROPRIETARIO`, `ASSINATURA_DIGITAL_VALIDA` | 6 |
| Omissão da identificação do proprietário | 1 | `ID_PROPRIETARIO` | 6, 7 |
| Divergência de altura-limite de muro | 1 | `MURO_ALTURA_MAX` | 8, 9 |
| Omissão da indicação do Norte | 1 | `NORTE_INDICADO` | 6 |
| **Total** | **11** | | |

**Consequências para o plano:**
- 8 dos 11 erros são de **completude** (ausências), não de valores. A base sintética (Fases 3 e 4) precisa ter conjuntos com cada uma dessas omissões e conjuntos completos, para medir os falsos alarmes.
- **Meta no real:** os 11 erros encontrados ou marcados para confirmação. Uma "validação técnica de assinatura" que dependa de consulta *online* conta como encontrada se o relatório a apontar como pendência a validar.

---

## 6. Quando a métrica não é atingida
1. O relatório de avaliação mostra em que **etapa** está a perda (tabela 3.3).
2. Criamos um caso sintético mínimo que reproduz o problema.
3. Corrigimos, rodamos a avaliação de novo e comparamos com a anterior (nenhuma métrica pode piorar sem justificativa).
