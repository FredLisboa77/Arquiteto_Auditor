# 02 — Proposta de MVP

> **MVP** (*Minimum Viable Product*, produto mínimo viável): a menor versão do software que já resolve o seu problema real de ponta a ponta — receber os PDFs de um projeto, apontar os problemas com evidência e gerar um relatório versionado para o autor.

---

## 1. Definição de "pronto" do MVP

O MVP está pronto quando você consegue, **no seu notebook, sem internet e sem digitar dados**:

1. Criar uma análise, arrastar os PDFs de um projeto (pranchas, matrícula, escritura, memorial, lei municipal, normas do condomínio).
2. Esperar alguns minutos enquanto o sistema lê tudo.
3. Revisar na tela os valores com baixa confiança (amarelos) e confirmar ou corrigir.
4. Ver a lista de itens classificados, editar observações e marcar itens.
5. Exportar o relatório **R00** em PDF e DOCX.
6. Semanas depois, enviar a revisão corrigida do mesmo projeto; o sistema sugere "é o mesmo projeto" (você confirma), gera o **R01** e mostra, item a item, o que foi **resolvido**, o que continua **pendente** e o que é **novo**.
7. E, na validação final, o sistema encontra os erros conhecidos do seu conjunto real (meta em `05-avaliacao.md`).

---

## 2. O que ENTRA no MVP

### 2.1 Entrada de documentos
- Upload de vários PDFs por análise.
- Classificação automática do tipo (prancha, matrícula, escritura, memorial, lei/consulta prévia, norma do condomínio) — **com possibilidade de você corrigir**.
- Detecção automática vetorial × escaneado **por página**.
- OCR em português (Tesseract) para páginas escaneadas, com pré-processamento (endireitar, limpar, binarizar).
- **Foco: pranchas exportadas do AutoCAD** (seu caso real). Outros softwares entram como variação de layout na base sintética, mas só serão "garantidos" em versões futuras.

### 2.2 Extração (cada valor com evidência e confiança)
- **Identificação:** título do projeto, autor, CAU/CREA, RRT/ART, revisão do carimbo, endereço, lote, quadra, condomínio, nº da matrícula, cartório.
- **Pranchas:** área do terreno, testada(s), área construída por pavimento, área total, recuos rotulados (frontal, laterais, fundos), TO, CA, área/taxa permeável, altura, nº de pavimentos — a partir de **quadro de áreas, carimbo, rótulos e cotas escritas**.
- **Matrícula e escritura:** nº da matrícula, cartório, área, dimensões/testada, confrontações (texto), lote/quadra; **lista de atos (R-n/AV-n)** e **estado atual** considerando averbações de retificação de área/medidas.
- **Memorial descritivo:** os mesmos campos numéricos e de identificação, quando presentes.
- **Parâmetros (prefeitura e condomínio):** área mínima do lote, testada mínima, recuos mínimos, TO máx., CA máx., permeabilidade mín., altura máx., nº máx. de pavimentos, **altura máxima de muro** — **cada um com trecho literal e página**, para a **zona** do lote.
- **Completude e apresentação:** cotas e dimensões essenciais escritas, indicação do Norte, identificação do proprietário, assinaturas (presença e integridade da assinatura digital). Ver §4.1.

### 2.3 Revisão humana
- Tela de "pendências de confirmação": tudo com baixa confiança, associação incerta, parâmetro ambíguo ou dado não encontrado. Cada item mostra o **recorte da página** de origem.
- Você pode confirmar, corrigir (o valor corrigido fica marcado como "informado pelo revisor") ou marcar "não se aplica".

### 2.4 Verificação (código determinístico)
- **Consistência documental:** mesmo dado em documentos diferentes → compara com tolerância configurável (ex.: áreas ±0,01 m²; arredondamento) → "divergente entre documentos".
- **Atendimento a parâmetros:** projeto × parâmetro → "atende" / "não atende", com **margem** (ex.: "TO 62,0% · máx. 60,0% · excede 2,0 p.p. — em terreno de 400 m², reduzir ≈ 8,0 m² de projeção").
- **Prefeitura × condomínio:** usa o mais restritivo e sinaliza.
- **Fórmulas:** usa a da lei quando encontrada; senão a padrão, declarada no relatório.
- Sem dado suficiente → "não foi possível verificar", com o motivo.

### 2.5 Relatório
- Tela de revisão do relatório (editar observações, marcar/desmarcar itens, reordenar não é necessário no MVP).
- Exportação **PDF e DOCX**, com cabeçalho completo (revisor, data, versão R0n, revisão do projeto, identificação), quatro classificações, evidência, margem, sugestão e **aviso de responsabilidade técnica**.
- Sugestões redigidas pelo LLM a partir de números calculados pelo código; **texto-modelo** de reserva se o LLM não estiver disponível.
- Apenas dados pessoais necessários (nome e registro do autor; nenhum CPF/RG/estado civil de proprietários, mesmo que constem da escritura).

### 2.6 Versionamento (obrigatório)
- Histórico local em banco SQLite: projetos, rodadas de análise, documentos (com *hash*, uma "impressão digital" do arquivo), extrações, confirmações, itens e relatórios emitidos.
- Reconhecimento de "mesmo projeto" por matrícula + lote + quadra + condomínio (+ título), **com confirmação sua**.
- Comparação R(n-1) → R(n) por chave estável do item: **resolvido / pendente / novo** (+ "não verificável agora").
- Relatórios antigos ficam imutáveis (congelados) depois de emitidos.

### 2.7 Base de testes e avaliação
- Base sintética (pranchas vetoriais variadas, matrículas/escrituras "escaneadas", memoriais, leis e normas fictícias, gabaritos JSON, projeto com R00 e R01).
- Script de avaliação com as métricas de `05-avaliacao.md`.

### 2.8 Configuração e segurança
- Configurações: nome do revisor, modelo de LLM, tolerâncias, limiares de confiança, pasta de dados.
- 100% local; nenhuma chamada a serviços externos durante a análise.
- Verificação anti-vazamento antes de cada commit.

---

## 3. O que FICA PARA DEPOIS

| Versão | Funcionalidade | Por que não agora |
|---|---|---|
| v1.1 | **Executável Windows + instalador** | Planejado desde o início (escolhas compatíveis), mas só empacotamos quando o MVP estiver validado. Pode ser a última fase do MVP se você preferir — ver `04-plano-de-fases.md`. |
| v1.1 | Pranchas de Revit, ArchiCAD, SketchUp/LayOut validadas com PDFs reais | Seu caso real é AutoCAD; precisamos de exemplos reais desses softwares para validar. |
| v1.2 | Edição das fórmulas de cálculo por município na interface | No MVP você ajusta num arquivo de configuração simples. |
| v1.2 | Biblioteca de municípios/condomínios (reaproveitar parâmetros já extraídos) | Útil quando houver vários projetos no mesmo lugar. |
| v1.3 | OCR alternativo (PaddleOCR/docTR) e LLM de visão para páginas muito ruins | Seu caso é texto digitado; Tesseract deve bastar. |
| v2 | Medir recuos/áreas na **geometria** vetorial | Muito mais complexo; suas medidas vêm escritas. |
| v2 | Manuscritos | Você não tem esse caso. |
| v2 | Multiusuário, login, vários escritórios, servidor | Uso profissional futuro. A arquitetura em camadas permite (ver `03-arquitetura.md`, §8). |
| v2 | Outras tipologias (multifamiliar, comercial, mais de 2 pavimentos) | Escopo atual: casas até 2 pavimentos em condomínio horizontal. |
| v2 | Verificações de acessibilidade, ventilação/iluminação de cômodos, vagas | Exigem ler a planta cômodo a cômodo. |
| — | Alterar os documentos do autor | **Nunca** (princípio do projeto). |

---

## 4. Lista de verificações do MVP (catálogo inicial de itens)

Cada item tem uma **chave estável** — é o que permite comparar R00 com R01.

| Chave | Verificação | Tipo |
|---|---|---|
| `ID_MATRICULA` | Nº da matrícula igual em prancha, memorial, certidão, escritura | Consistência |
| `ID_CARTORIO` | Cartório coincidente | Consistência |
| `ID_LOTE_QUADRA` | Lote e quadra coincidentes | Consistência |
| `ID_CONDOMINIO` / `ID_ENDERECO` | Nome do condomínio / endereço coincidentes | Consistência |
| `ID_AUTOR_REGISTRO` | Autor e CAU/CREA presentes e iguais entre pranchas/memorial; RRT/ART presente | Consistência / presença |
| `ID_REVISAO` | Mesma revisão em todas as pranchas do conjunto | Consistência |
| `TERRENO_AREA` | Área do terreno: prancha × memorial × matrícula (estado atual) × escritura | Consistência |
| `TERRENO_TESTADA` | Testada: prancha × matrícula × escritura | Consistência |
| `AREA_CONSTR_PAV_n` / `AREA_CONSTR_TOTAL` | Áreas por pavimento e total: quadro × memorial; soma dos pavimentos = total | Consistência / aritmética |
| `LOTE_AREA_MIN` | Área do lote ≥ mínima | Parâmetro |
| `LOTE_TESTADA_MIN` | Testada ≥ mínima | Parâmetro |
| `RECUO_FRONTAL` / `RECUO_LATERAL_E` / `RECUO_LATERAL_D` / `RECUO_FUNDOS` | Recuo ≥ mínimo | Parâmetro |
| `TO_MAX` | Taxa de ocupação ≤ máxima (e TO declarada = TO recalculada) | Parâmetro / aritmética |
| `CA_MAX` | Coeficiente de aproveitamento ≤ máximo (e declarado = recalculado) | Parâmetro / aritmética |
| `PERMEAVEL_MIN` | Área/taxa permeável ≥ mínima (e declarada = recalculada) | Parâmetro / aritmética |
| `ALTURA_MAX` | Altura ≤ máxima | Parâmetro |
| `PAVIMENTOS_MAX` | Nº de pavimentos ≤ máximo | Parâmetro |
| `MURO_ALTURA_MAX` | Altura de muro/fechamento (divisa e frente) ≤ máxima; altura indicada em corte/fachada/memorial coerente | Parâmetro / consistência |
| `PARAM_CONFLITO_*` | Prefeitura e condomínio divergem → adotado o mais restritivo (informativo) | Sinalização |

### 4.1 Verificações de completude e apresentação

Incluídas após a descrição dos erros do conjunto real: 8 dos 11 erros conhecidos são de **omissão** ou **indefinição**, não de valores. Classificação: ausência → "não atende" (requisito de apresentação); presença sem confirmação possível → "não foi possível verificar".

O conjunto mínimo exigido vem de um arquivo configurável `requisitos_apresentacao.toml`, com uma lista padrão. Quando o Código de Obras ou a norma do condomínio listar exigências de apresentação, elas são extraídas como os demais parâmetros, com trecho e página.

| Chave | Verificação | Como |
|---|---|---|
| `COTA_INDEFINIDA` (escopo: elemento) | Dimensões essenciais escritas: testadas e lados do lote, recuos, altura total, altura de muro, dimensões externas da edificação. Também identifica dimensão apenas "gráfica" (desenhada, mas sem cota numérica). | Para cada dimensão esperada, procurar um valor rotulado ou uma cota associada. Linha de cota sem texto próximo, ou dimensão esperada ausente → item. |
| `NORTE_INDICADO` | Indicação do Norte nas plantas de situação e de localização | Texto "N"/"NORTE" isolado junto a um símbolo vetorial (seta ou rosa dos ventos) na prancha de situação/localização. Ausente → "não atende"; símbolo incerto → confirmação. |
| `ID_PROPRIETARIO` | Identificação do proprietário presente no carimbo e/ou memorial e coerente com a matrícula | Detecta o campo e compara localmente com o proprietário do estado atual da matrícula. **O relatório indica a omissão ou a divergência sem reproduzir dados pessoais além do nome.** |
| `ASSINATURA_AUTOR` / `ASSINATURA_PROPRIETARIO` | Assinaturas presentes onde exigido (pranchas, memorial) | Assinatura digital: campos de assinatura do PDF. Assinatura escaneada ou imagem: imagem no campo de assinatura do carimbo, com baixa confiança e confirmação. |
| `ASSINATURA_DIGITAL_VALIDA` | Integridade da assinatura digital (documento não alterado após assinar) e identificação do certificado | **pyHanko**, localmente: verifica a integridade e lê o titular e o emissor. A validação completa da cadeia ICP-Brasil exige os certificados-raiz do ITI, que podem ser guardados localmente. A consulta de revogação e a validação oficial no validador do ITI (validar.iti.gov.br) ficam como **orientação** no relatório, para o usuário fazer manualmente. O software não envia o documento a nenhum serviço. |
