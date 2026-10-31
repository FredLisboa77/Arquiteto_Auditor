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

## 2. Formato do gabarito (definido na Fase 2)

- **Exemplo comentado:** [`docs/esquemas/exemplo_gabarito.json`](esquemas/exemplo_gabarito.json)
- **Esquema** (regras do formato; o VS Code usa para autocompletar): [`docs/esquemas/gabarito.schema.json`](esquemas/gabarito.schema.json)
- **Validador:** `arquiteto_auditor.avaliacao.gabarito.carregar_gabarito()`. Ele lista todos os erros de uma vez, em português.

| Campo | Obrigatório | Conteúdo |
|---|---|---|
| `conjunto` | sim | Identificador do conjunto (minúsculas, números e hífen), ex.: `sint-007` |
| `versao_gabarito` | sim | Número inteiro ≥ 1; aumenta quando o gabarito é corrigido |
| `rodada` | sim | `R00`, `R01`… |
| `conjunto_anterior` | se houver comparação | Conjunto da rodada anterior (ex.: o R00 de um R01) |
| `reservado_avaliacao` | não | `true` para conjuntos que não podem ser usados no desenvolvimento (§4) |
| `descricao`, `zona` | não | Texto livre / zona urbanística do lote |
| `valores_esperados` | não | Por chave, o valor em cada fonte: `prancha`, `memorial`, `matricula` (estado atual), `escritura`, `consulta_previa`, `lei_municipal`, `norma_condominio`, `prefeitura`, `condominio`, `adotado`, `calculado` |
| `itens_esperados` | sim | Lista de `{chave, escopo?, status, descricao?, documentos?, valor_projeto?, limite?}`. `status` ∈ `atende`, `nao_atende`, `divergente`, `nao_verificavel` |
| `comparacao_rodada_anterior` | não (proibido em R00) | Lista de `{chave, escopo?, resultado}`. `resultado` ∈ `resolvido`, `pendente`, `novo`, `nao_verificavel_agora` |

Regras verificadas automaticamente:
- toda chave precisa existir no catálogo;
- chaves com escopo (`AREA_CONSTR_PAV`, `COTA_INDEFINIDA`) exigem `escopo`, e as demais não podem tê-lo;
- não pode haver item duplicado.

**Erros esperados** (a base da revocação) são os itens com `nao_atende` ou `divergente`.

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

## 5.2 Exemplos reais de calibração

Em 30/10/2026, o usuário trouxe dois exemplos reais **sem gabarito**: uma planta baixa e um projeto executivo completo. Eles ficam em `dados_privados/desenvolvimento/` e servem **só para calibrar** as regras de leitura (rótulos, layouts, posição das cotas). Não entram nas métricas.

São examinados apenas pela versão mascarada, gerada por `scripts/mascarar_pdf.py` na máquina do usuário e conferida por ele antes de ser compartilhada: posições e termos técnicos visíveis, dados pessoais mascarados. O conjunto original, com os 11 erros conhecidos, continua reservado para a validação final.

## 6. Quando a métrica não é atingida
1. O relatório de avaliação mostra em que **etapa** está a perda (tabela 3.3).
2. Criamos um caso sintético mínimo que reproduz o problema.
3. Corrigimos, rodamos a avaliação de novo e comparamos com a anterior (nenhuma métrica pode piorar sem justificativa).
