# Arquiteto Auditor

Ferramenta **local** e de **código aberto** de apoio à conferência documental de projetos arquitetônicos residenciais (casas de até dois pavimentos em condomínio horizontal, Brasil).

Lê os PDFs do projeto (pranchas, memorial descritivo, certidão de inteiro teor da matrícula, escritura, legislação municipal e normas do condomínio), verifica a consistência entre os documentos e o atendimento aos parâmetros urbanísticos, e gera um relatório versionado (R00, R01…) com evidências e sugestões de correção para o autor do projeto.

> ⚠️ **Ferramenta de apoio.** Não substitui a análise profissional. A responsabilidade técnica permanece com os profissionais habilitados (CAU/CREA, RRT/ART).

**Status:** fase de planejamento. Veja [docs/](docs/).

## Princípios
- 100% local: nenhum documento sai do seu computador (LGPD).
- Cálculos por código determinístico; IA local só para interpretar texto e redigir.
- Toda conclusão com evidência rastreável (arquivo, página, trecho).
- Apenas ferramentas gratuitas e de código aberto.

## Preparar o ambiente (Windows)
```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\pre-commit install          # ativa a verificação anti-vazamento
.venv\Scripts\python scripts\verificar_ambiente.py
.venv\Scripts\python -m pytest
```
Pré-requisitos: Tesseract com português e Ollama. Detalhes em [docs/03-arquitetura.md](docs/03-arquitetura.md) §6.

## Licença
[GNU AGPL-3.0](LICENSE).
