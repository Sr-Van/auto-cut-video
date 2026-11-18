# Plano de Evolução e Melhorias — AutoCortesBR (`plano_carbon.md`)

Este documento consolida, em ordem de prioridade e dependência técnica, as melhorias mapeadas na revisão completa do **AutoCortesBR** (`core/`, `gui/`, `utils/`, `tests/` e `site/`).

---

## 🎯 Princípios de Execução

1. **100% local, zero SaaS:** nenhuma dependência externa obrigatória de nuvem, contas ou banco remoto; processamento pesado segue local (`FFmpeg` + `faster-whisper` + `OpenCV/YuNet`).
2. **Compatibilidade retroativa:** preferências persistidas em `QSettings` (`ProcessingOptions.from_json`) e históricos em `output/projetos.json` devem continuar carregando sem quebrar.
3. **Validação contínua:** cada etapa implementada deve atualizar ou adicionar testes automatizados em `tests/` (com `pytest`).
4. **Entregas incrementais:** cada subitem pode ser entregue em um commit/PR coeso, na ordem exata das fases abaixo (P0 → P1 → P2).

---

## 📅 Fases de Execução

### Fase 1 (P0) · Base Segura: Ambiente, Subprocessos Windows e Parsing

- [x] **1.1. Declarar dependências completas em `requirements.txt`**
  - **Arquivos:** `requirements.txt`, `core/captions/fonts.py`.
  - **Problema:** `from PIL import ImageFont` é importado logo na inicialização de `main.py` e `site/server.py`, porém `Pillow` não consta em `requirements.txt`, quebrando instalações limpas do zero.
  - **Solução:** Adicionar `Pillow` (e faixas mínimas compatíveis das bibliotecas principais como `PySide6`, `opencv-python`, `faster-whisper`, `httpx`, `python-dotenv`, `yt-dlp[default]`).
  - **Critério de aceite:** Instalação limpa a partir de `requirements.txt` executa `main.py`, `site/server.py` e `core.captions.fonts` sem `ModuleNotFoundError`.

- [x] **1.2. Subprocessos silenciosos e UTF-8 seguro no Windows**
  - **Arquivos:** `core/exceptions.py` (`run_interruptible_cmd`), `core/render.py` (`_probe_encoder`, `_probe_has_audio`), `core/video_ops.py` (`get_duration`).
  - **Problema:** Ao contrário de `core/framing.py` e `gui/thumbnails.py`, esses pontos chamam `subprocess.Popen` / `subprocess.run` sem `CREATE_NO_WINDOW` (o que abre janelas de console piscando em builds GUI sem terminal) e usam `text=True` sem `encoding="utf-8", errors="replace"` (sujeito a `UnicodeDecodeError` no codec `cp1252` do Windows quando o FFmpeg imprime títulos/caminhos UTF-8 no `stderr`).
  - **Solução:** Centralizar flags padrão (`creationflags=subprocess.CREATE_NO_WINDOW` quando `sys.platform == "win32"`) e `encoding="utf-8", errors="replace"` em `run_interruptible_cmd` e nos helpers de `probe`.
  - **Critério de aceite:** Nenhum `subprocess` em `core/` abre janela de console no Windows nem falha ao decodificar saída com acentos/emojis.

- [x] **1.3. Parser resiliente de timestamps e sanitização pós-IA**
  - **Arquivos:** `utils/timefmt.py` (`hhmmss_to_seconds`), `core/ai_analyzer.py` (`_filter_by_score`), `tests/test_timefmt.py`.
  - **Problema:** `hhmmss_to_seconds` converte segundos com `int(parts[2])`, lançando `ValueError` se algum modelo retornar milissegundos (`00:01:23.450` ou `00:01:23,5`) em modo fallback de prompt. Além disso, `_filter_by_score` não descarta clipes com `end <= start` ou timestamps inválidos antes da normalização.
  - **Solução:** Aceitar segundos fracionários (`float` normalizando `,` → `.`) em `hhmmss_to_seconds` e validar/descartar intervalos malformados ou invertidos (`end <= start`) já em `_filter_by_score`.
  - **Critério de aceite:** Timestamps `HH:MM:SS`, `MM:SS` e com decimais (`00:01:23.450`) são convertidos corretamente; clipes com `end <= start` são filtrados sem quebrar o pipeline.

---

### Fase 2 (P0) · Qualidade Direta dos Cortes, Zoom Dinâmico e Legendas

- [x] **2.1. Corrigir ativação do zoom dinâmico (`follow_dynamic`) e máscara de fala (`follow`)**
  - **Arquivos:** `core/video_ops.py` (`_process_vertical`, `_clip_words`), `core/framing.py` (`analyze_clip`, `plan_from_tracks`), `core/pipeline.py`.
  - **Problema:** Na configuração padrão (`captions_enabled=False` e `caption_transcribe_mode="clip"`), `pipeline.py` transcreve com `word_timestamps=False`, deixando `seg.words` vazio. Em `_process_vertical`, `framing.analyze_clip` executa **antes** de `_clip_words` e consulta apenas `segments`, recebendo `words=[]`. Consequências:
    1. Em `follow_dynamic`, `if dynamic and words and plan.shots:` falha silenciosamente (`plan.beats = []`), desativando o zoom dinâmico.
    2. Em `follow`, `speaking = [True] * n_frames` trata pausas como fala contínua.
    3. `.cache/framing_NNN.json` grava o plano sem ciclos em disco sem incluir presença de palavras na chave.
  - **Solução:**
    - Resolver as palavras da janela (`_clip_words` ou transcrição leve do trecho quando `layout.dynamic` estiver ativo mesmo com legendas desligadas) **antes** de `framing.analyze_clip`.
    - Reutilizar a mesma lista `words` tanto no enquadramento quanto na geração do `.ass` (sem retranscrever duas vezes).
    - Incluir `"has_words": bool(words)` (e versão de algoritmo atualizada) na `cache_key` do `framing`.
  - **Critério de aceite:** `follow_dynamic` gera `ZoomBeat`s reais com `captions_enabled=False` ou `True` (nos modos `"clip"` e `"full"`); o cache invalida automaticamente planos antigos sem palavras.

- [x] **2.2. Ajustar `PADDING_S` e impedir estouro de `max_clip_duration` no merge**
  - **Arquivos:** `core/config.py` (`PADDING_S`), `core/options.py`, `utils/normalize.py` (`normalize_clips`), `core/video_ops.py` (`_cut_window`), `utils/report.py`, `tests/test_normalize.py`.
  - **Problema:**
    - `PADDING_S = 5` adiciona **+10s totais** (5s antes do gancho, matando os primeiros 3s de retenção, e 5s depois do desfecho, trazendo de volta CTAs/despedidas que o prompt pediu para cortar e empurrando clipes de 90s para 100s).
    - `normalize_clips` funde quaisquer clipes sobrepostos sem verificar se a união ultrapassa `max_duration`.
    - `relatorio.json` exibe os timestamps pré-padding, divergindo da duração real do MP4 exportado.
  - **Solução:**
    - Reduzir o padrão de `PADDING_S` para `0.3`s (margem fonética mínima; usuário ainda pode aumentar em Ajustes se desejar).
    - Em `normalize_clips`, ao detectar sobreposição entre dois candidatos, só fundir se `(max(last_e, entry_e) - last_s) <= max_duration`; caso contrário, manter apenas o trecho de maior `viral_score` ou aparar a fronteira sem sobreposição.
    - Registrar no clipe/relatório a janela efetiva cortada quando aplicável.
  - **Critério de aceite:** Clipes gerados abrem imediatamente no gancho, nunca ultrapassam `max_clip_duration` + padding mínimo após merge, e mantêm sincronia de tempo entre UI e MP4.

- [x] **2.3. Respeitar `caption_margin_bottom` nos presets e Ajustes**
  - **Arquivos:** `core/layouts.py` (`caption_options`), `gui/widgets.py` (`PhonePreviewWidget._draw_caption`), `gui/settings_dialog.py`, `tests/test_layouts.py`, `tests/test_captions_presets.py`.
  - **Problema:** `layouts.caption_options(options)` recalcula e sobrescreve incondicionalmente `adjusted.caption_margin_bottom` com `layout.caption_anchor`. Na prática, isso anula tanto a altura própria definida em cada preset de `VIRAL_PRESETS` (ex.: `280`, `380`, `560`, `640`) quanto o controle `"Margem inferior (px)"` em Ajustes → Legenda.
  - **Solução:**
    - Nos layouts de tela cheia (`center`, `follow`, `follow_dynamic`), respeitar `options.caption_margin_bottom` escalado proporcionalmente pela altura (`options.height / 1920.0`).
    - Nos layouts multi-slot (`react`, `title_middle`, `image_video`), manter o posicionamento ancorado dentro de `caption_slot` (com suporte opcional a ajuste relativo seguro dentro do slot) para nunca invadir faixa de texto/webcam.
    - Na GUI, sinalizar claramente quando o layout multi-slot controla a posição vertical da legenda.
  - **Critério de aceite:** Alterar `"Margem inferior"` ou trocar entre presets com alturas diferentes reflete imediatamente na prévia 9:16 e no vídeo renderizado via `libass`.

---

### Fase 3 (P1) · Performance de Transcrição, Áudio Comercial e Precisão de Render

- [ ] **3.1. Whisper com Silero VAD (`vad_filter=True`), progresso granular e default inteligente**
  - **Arquivos:** `core/transcriber.py` (`transcribe`, `get_model`), `core/pipeline.py`, `core/config.py` (`WHISPER_MODEL`).
  - **Problema:** Sem `vad_filter=True`, o `faster-whisper` processa silêncios e músicas de fundo, aumentando o tempo de execução e gerando frases alucinadas em legendas. Além disso, o progresso da transcrição fica estagnado em `20%` até o último segmento, e `WHISPER_MODEL="large"` sem GPU torna o primeiro uso extremamente lento.
  - **Solução:**
    - Ativar `vad_filter=True` com parâmetros conservadores (ex.: `min_silence_duration_ms=500`, `speech_pad_ms=200`) na chamada `model.transcribe`.
    - Aceitar `progress_callback` opcional em `transcribe(...)` e emitir progresso contínuo usando `seg.end / info.duration` (mapeado entre `20%` e `48%` no pipeline).
    - Avaliar/definir `"turbo"` como modelo padrão quando não houver override no `.env` (ou seleção automática CUDA → `"large"` / CPU → `"turbo"`).
  - **Critério de aceite:** Barra de progresso avança suavemente durante a transcrição, silêncios longos são pulados sem alucinações e o tempo de transcrição em CPU cai significativamente.

- [ ] **3.2. Normalização de loudness (`-14 LUFS`) nos cortes exportados**
  - **Arquivos:** `core/options.py` (`audio_normalize: bool = True`), `core/render.py` (`build_music_filter`, `render_clip`), `gui/settings_dialog.py`.
  - **Problema:** Áudios de lives, cortes de podcasts e gravações caseiras chegam com volume baixo ou picos inconsistentes frente a outros Shorts/Reels.
  - **Solução:** Adicionar opção `audio_normalize` em `ProcessingOptions` (ligada por padrão) aplicando filtro `loudnorm=I=-14:TP=-1.5:LRA=11` na trilha de áudio principal (ou na saída final quando houver música de fundo) se o vídeo possuir trilha de áudio.
  - **Critério de aceite:** Clipes exportados saem em volume comercial consistente sem distorção ou clipping, com opção de desativar nos Ajustes.

- [ ] **3.3. FPS real no `sendcmd`, remoção da cópia dupla de fontes e fallback automático de encoder**
  - **Arquivos:** `core/framing.py` (`probe_size` → `probe_video_info`), `core/render.py` (`dynamic_crop_rects`, `_dynamic_focus_slot`, `build_layout_filter`, `render_clip`), `core/video_ops.py` (`_write_clip_captions`).
  - **Problema:**
    1. `dynamic_crop_rects` usa `fps: float = 30.0` fixo e slots de texto/imagem usam `r=30` / `fps=30`, gerando micro-stutter quando o vídeo de origem é `60fps` ou `24fps`.
    2. `_write_clip_captions` copia todas as ~14 fontes de `assets/fonts` para `autocut_caps_*`, e logo depois `render_clip` copia tudo de novo para `autocut_render_*`.
    3. Em GPUs consumer NVIDIA (`h264_nvenc`), `max_workers > 2` pode falhar por limite de sessões simultâneas de NVENC e abortar o clipe sem tentar fallback para `libx264`.
  - **Solução:**
    - Fazer probe da taxa de quadros real (`r_frame_rate` / `avg_frame_rate` via `ffprobe`) e passar para `dynamic_crop_rects` e slots gerados.
    - Apontar `fontsdir` direto para `BUNDLED_FONTS_DIR` (ou diretório temporário único quando houver fonte externa do sistema), eliminando cópias redundantes por clipe.
    - Em `render_clip`, se `encoder != "libx264"` e o FFmpeg retornar erro com `encoder` automático, registrar aviso no log e repetir o clipe automaticamente com `libx264`.
  - **Critério de aceite:** Vídeos 60fps mantêm movimento suave no zoom dinâmico; I/O temporário por clipe diminui; falhas transitórias de sessão GPU fazem fallback transparente para CPU.

---

### Fase 4 (P1) · Escalabilidade de IA para Lives Longas, Catálogo e Cache

- [ ] **4.1. Higienizar catálogo de modelos e validar disponibilidade em `resolve_targets`**
  - **Arquivos:** `core/config.py` (`PROVIDERS_CATALOG`), `core/providers/factory.py` (`resolve_targets`), `tests/test_providers.py`.
  - **Problema:** `PROVIDERS_CATALOG["google"]["models"]` contém IDs especulativos/inexistentes (ex.: `gemini-3.8-flash`, `gemini-3.6-flash`) à frente de modelos válidos, causando múltiplos `HTTP 404` desnecessários antes de acertar um modelo ativo, pois `resolve_targets` não valida contra `fetch_models`.
  - **Solução:** Revisar e manter em `PROVIDERS_CATALOG` apenas modelos reais vigentes, priorizando os mais confiáveis para JSON estruturado, e adicionar cache de sessão opcional de modelos ativos retornados por `/models` para pular modelos inexistentes logo no agendamento.
  - **Critério de aceite:** Primeira chamada por provedor configurado evita `404` em cascata mantendo compatibilidade com os mocks em `tests/test_providers.py`.

- [ ] **4.2. Chunking inteligente de transcrições longas (podcasts/lives de 2h–4h)**
  - **Arquivos:** `core/ai_analyzer.py` (`build_transcript_block`, `analyze`), novo helper de janelamento + testes dedicados.
  - **Problema:** Enviar 100% da transcrição numa única chamada estoura o TPM gratuito de provedores como Groq (`413` / rate limit por tokens) em vídeos de 2h+ e provoca perda de atenção no meio do vídeo (*lost-in-the-middle*).
  - **Solução:**
    - Definir limiar de duração/caracteres (ex.: acima de ~35–40 min ou ~45k chars): dividir a lista de segmentos em janelas contínuas alinhadas em `pause_gap` com ~2 minutos de overlap entre janelas adjacentes.
    - Executar `analyze` em cada janela com o agendador multi-chave/modelo (com progresso proporcional de `50%` a `65%`).
    - Consolidar os candidatos de todas as janelas, deduplicar sobreposições mantendo o maior `viral_score` e truncar para `max_clips`.
  - **Critério de aceite:** Vídeos longos (2h+) são analisados sem erro `413`, distribuindo cortes de alta qualidade do início ao fim da gravação.

- [ ] **4.3. Cache por hash de janela, cache da análise de IA e organização de downloads**
  - **Arquivos:** `core/cache.py`, `core/video_ops.py`, `core/pipeline.py`, `core/downloader.py`, `tests/test_cache.py`.
  - **Problema:**
    - `clip_001.json` e `framing_001.json` usam índice ordinal no nome do arquivo: se os cortes mudarem de ordem ou quantidade, o cache invalida e sobrescreve o anterior.
    - Mudar apenas preset de legenda, `layout_id` ou resolução obriga a consultar a IA novamente (consumindo cota e podendo gerar cortes diferentes).
    - `pipeline.py` passa `output_dir` direto ao `downloader.download_video`, salvando o vídeo bruto completo do YouTube na raiz de `output/` em vez de uma pasta dedicada/reutilizável.
  - **Solução:**
    - Nomear caches de trecho por hash determinístico de `(video_hash, cut_start, cut_end)` (`clip_<hash>.json`, `framing_<hash>.json`).
    - Persistir o resultado bruto da análise IA em `.cache/analysis_<hash>.json` (chaveado por `transcript_key + prompt_params_hash`), permitindo re-renderizar estilos/formatos instantaneamente sem nova chamada de IA (com flag `force` para ignorar).
    - Salvar downloads do YouTube em subpasta organizada (`output/_downloads/` ou dentro da pasta do projeto) reutilizando vídeo já baixado pelo `video_id`.
  - **Critério de aceite:** Reprocessar o mesmo vídeo alterando apenas legenda/formato não consome API de IA nem retranscreve trechos já renderizados.

---

### Fase 5 (P2) · UX do Criador e Segurança do Web Studio

- [ ] **5.1. Gerenciador de API Keys na própria interface gráfica**
  - **Arquivos:** `core/config.py` (`reload_api_keys`), `gui/settings_dialog.py`, `gui/main_window.py`, `gui/ai_model_picker.py`.
  - **Problema:** Hoje `API_KEYS` é lido uma única vez na importação de `core/config.py`. Criadores não-técnicos precisam editar `.env` manualmente e reiniciar o programa — um bloqueio direto caso o app seja distribuído como `.exe`.
  - **Solução:**
    - Adicionar painel de **Chaves de API** em `Ajustes → Cortes & IA` permitindo inserir múltiplas chaves (identificando o provedor automaticamente pelo prefixo, com máscara visual e botão "Testar chave").
    - Persistir de forma segura localmente (ou atualizar `.env` do workspace com reload dinâmico via `reload_api_keys()`), atualizando imediatamente o `AIModelPicker` e o badge de status na tela principal sem reiniciar.
  - **Critério de aceite:** Usuário configura uma chave pela GUI, testa a conexão, escolhe o modelo e processa sem editar arquivos nem reiniciar o app.

- [ ] **5.2. Fluxo de revisão pré-render e atalhos de publicação**
  - **Arquivos:** `gui/main_window.py`, `gui/projects_dialog.py`, `gui/controllers/pipeline_controller.py`.
  - **Problema:**
    - Nos cards de corte, há `"Copiar caminho"`, mas não há botão para copiar **Título + Descrição** formatados para colar no YouTube Shorts / TikTok / Reels.
    - Todos os cortes escolhidos pela IA são renderizados de uma vez antes de o criador poder descartar cortes indesejados ou ajustar ±1–2 segundos no início/fim.
  - **Solução:**
    - Adicionar botão `"Copiar título + descrição"` nos cards de resultado (`main_window.py`) e nos itens expandidos de `ProjectsDialog`.
    - Adicionar modo opcional `"Revisar cortes antes de renderizar"` (checkbox na configuração rápida ou Ajustes): pausa o fluxo após a análise/normalização, exibe a lista com checkbox de aprovação + ajuste fino de `start`/`end` e botão `"Renderizar selecionados"`.
  - **Critério de aceite:** Cópia de título + descrição funciona com feedback visual nos dois painéis; revisão pré-render permite renderizar apenas os cortes aprovados com tempos ajustados.

- [ ] **5.3. Endurecimento de segurança e cancelamento no Web Studio (`site/server.py`)**
  - **Arquivos:** `site/server.py`, `site/assets/studio.js`.
  - **Problema:**
    - Os endpoints `POST /api/run` e `POST /api/upload` aceitam requisições sem validar `Origin`/`Host`, expondo o servidor local (`127.0.0.1:8000`) a CSRF caso o usuário visite um site malicioso com o servidor aberto.
    - Não há endpoint `POST /api/cancel` conectado ao `cancel_event`.
    - Uploads temporários em `UPLOAD_DIR` nunca são removidos no encerramento; com `--host 0.0.0.0`, qualquer cliente na rede pode informar caminhos arbitrários do sistema em `video_path` / `output_dir`.
  - **Solução:**
    - Validar `Origin`/`Referer` contra `Host` permitido em todas as rotas `POST`.
    - Criar `cancel_event` por job em `_run_job` e expor `POST /api/cancel` com botão correspondente em `studio.js`.
    - Registrar limpeza de `UPLOAD_DIR` via `atexit` e bloquear caminhos fora das pastas permitidas quando rodando em interface não-loopback.
  - **Critério de aceite:** Requisições `POST` cross-origin são rejeitadas com `403`, cancelamento interrompe FFmpeg/Whisper pelo navegador e arquivos temporários de upload são limpos ao encerrar.

---

### Fase 6 (P2) · Manutenibilidade, Limpeza e Testes de Integração

- [ ] **6.1. Remoção de código morto e modularização da camada `gui/`**
  - **Arquivos:** `core/captions/ass_writer.py`, `core/config.py`, `core/ai_analyzer.py`, `gui/main_window.py`, `gui/settings_dialog.py`, `gui/widgets.py`.
  - **Problema:**
    - Existem trechos sem uso ativo (`generate_swing_tags` em `ass_writer.py`, combo oculto `self.caption_preset` e método `_apply_preset` em `settings_dialog.py`, e aliases legados `GEMINI_*` / `_KeyTarget`).
    - `gui/main_window.py` (1.539 linhas), `gui/widgets.py` (1.426 linhas) e `gui/settings_dialog.py` (1.354 linhas) concentram múltiplas responsabilidades, dificultando manutenção e revisão.
  - **Solução:**
    - Remover código morto após verificar referências via grep/testes (mantendo apenas compatibilidade exigida por testes existentes ou migrando os testes juntos).
    - Extrair componentes independentes (`gui/phone_preview.py`, `gui/font_combo.py`, `gui/result_card.py`, `gui/settings_tabs/`), mantendo imports públicos preservados.
  - **Critério de aceite:** Toda a suíte `pytest` passa após a modularização, com módulos de GUI abaixo de ~500 linhas por arquivo.

- [ ] **6.2. Testes de integração do pipeline e receita de empacotamento Windows (`.exe`)**
  - **Arquivos:** `tests/test_pipeline_integration.py`, `tests/test_video_ops.py`, documentação/spec de build (`build/` ou `README.md`).
  - **Problema:** Os testes unitários atuais cobrem bem módulos isolados, mas não exercitam `core.pipeline.run` e `core.video_ops._process_vertical` de ponta a ponta (justamente onde surgiu o bug silencioso do `follow_dynamic`). Além disso, ainda falta definir o empacotamento standalone mencionado em `PRODUCT.md`.
  - **Solução:**
    - Criar testes de integração com mocks leves de `yt-dlp`, `faster-whisper`, `httpx` e `ffmpeg` validando o fluxo completo (`run` → `normalize_clips` → `_process_vertical` → `save_report` → `register_project`), incluindo `follow_dynamic`, `caption_margin_bottom`, cancelamento e fallback de encoder.
    - Validar `pytest` + ambiente de desenvolvimento (`requirements-dev.txt`) e documentar receita reproduzível de empacotamento Windows (PyInstaller + `assets/fonts/` + `core/models/*.onnx` + aviso/verificação de `ffmpeg`).
  - **Critério de aceite:** Suíte completa roda com `pytest` cobrindo fluxo ponta a ponta e regressões críticas da Fase 1–4.

---

## 📊 Matriz de Prioridade, Impacto, Esforço e Risco

| Fase / Item | Prioridade | Impacto no Produto | Esforço | Risco |
| :--- | :---: | :---: | :---: | :---: |
| **1.1–1.3 Base Segura (`requirements`, Windows, timestamps)** | **P0** | Alto | Baixo | Muito Baixo |
| **2.1 Correção `follow_dynamic` e `words` no `framing`** | **P0** | Crítico | Baixo | Baixo |
| **2.2 Ajuste `PADDING_S` + `max_duration` no merge** | **P0** | Crítico | Baixo | Baixo |
| **2.3 Respeitar `caption_margin_bottom` nos layouts/presets** | **P0** | Alto | Baixo | Baixo |
| **3.1 Whisper `vad_filter=True` + progresso real** | **P1** | Alto | Baixo | Baixo |
| **3.2 Normalização de loudness `-14 LUFS`** | **P1** | Alto | Baixo | Baixo |
| **3.3 FPS real `sendcmd` + fontes + fallback encoder** | **P1** | Médio-Alto | Médio | Baixo |
| **4.1 Higienização do catálogo + validação viva** | **P1** | Alto | Baixo | Baixo |
| **4.2 Chunking de lives/podcasts longos (2h–4h)** | **P1** | Muito Alto | Médio | Médio |
| **4.3 Cache por hash de janela + cache IA + downloads** | **P1** | Alto | Médio | Médio |
| **5.1 Gerenciador de API Keys na GUI** | **P2** | Alto | Médio | Baixo |
| **5.2 Revisão pré-render + copiar título/descrição** | **P2** | Alto | Médio-Alto | Médio |
| **5.3 Segurança CSRF/cancelamento no `site/server.py`** | **P2** | Médio | Baixo | Baixo |
| **6.1–6.2 Limpeza, modularização GUI, testes E2E e `.exe`** | **P2** | Alto (longo prazo) | Alto | Médio |

---

## 🧭 Ordem Recomendada de Execução

1. **Sprint 1 (Estabilidade & Qualidade P0):** Executar **Fase 1 (1.1 → 1.3)** e **Fase 2 (2.1 → 2.3)**. Resolve imediatamente os bugs reais de entrega do clipe (`follow_dynamic` inativo, 5s de pré-contexto antes do gancho, margem de legenda ignorada, travamentos no Windows e `Pillow` faltante).
2. **Sprint 2 (Velocidade & Áudio P1):** Executar **Fase 3 (3.1 → 3.3)**. Melhora velocidade percebida, qualidade de transcrição, fluidez a 60fps e volume profissional dos vídeos.
3. **Sprint 3 (Escala & Cota de IA P1):** Executar **Fase 4 (4.1 → 4.3)**. Habilita processamento confiável de podcasts/lives de várias horas sem esgotar cota gratuita nem desperdiçar chamadas ao ajustar legenda/formato.
4. **Sprint 4 (Produto & Sustentação P2):** Executar **Fase 5 (5.1 → 5.3)** e **Fase 6 (6.1 → 6.2)**. Prepara o AutoCortesBR para uso por criadores não-técnicos, publicação mais ágil e base limpa para evoluções futuras.
