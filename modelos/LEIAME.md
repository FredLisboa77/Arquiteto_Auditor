# modelos/ — não versionado

Modelos de IA e de OCR são grandes (centenas de MB a alguns GB) e não vão para o Git.

- **LLM (Ollama):** os modelos ficam na pasta do próprio Ollama. Para guardá-los no disco D:, defina a variável de ambiente `OLLAMA_MODELS=D:\ollama\models` (veja `docs/03-arquitetura.md`).
- **Tesseract:** o arquivo de idioma `por.traineddata` vem com o instalador do Tesseract. Esta pasta pode guardar versões alternativas (por exemplo, `tessdata_best`).

Como baixar cada modelo: `docs/03-arquitetura.md`, seção "Modelos e distribuição".
