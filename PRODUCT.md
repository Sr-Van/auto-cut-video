# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Solo content creators and channel owners using AutoCortesBR on their own machine to quickly turn long-form videos into short vertical clips ready to publish on Reels, YouTube Shorts, and TikTok.

## Product Purpose

AutoCortesBR automates the path from a long video (YouTube link or local video file) to ready-to-post 9:16 vertical clips. It transcribes speech locally, asks AI models to select high-potential moments with titles, hooks, descriptions, and viral scores, renders cropped vertical clips with optional animated word-by-word captions, and keeps an organized local registry of projects and publication status. Success means cutting production time from raw footage to upload without manual timeline scrubbing or cloud subscriptions.

## Positioning

A 100% local, zero-SaaS video clipping workstation tailored for Brazilian creators: heavy media processing (`FFmpeg` + `faster-whisper`) stays entirely on the user's machine with no login, backend server, or billing, combined with resilient multi-provider AI key rotation and one-click PT-BR viral caption presets.

## Operating Context

- **Primary surface:** Desktop application built with Python and `PySide6` (`main.py`, `gui/`), structured around three main views (`Cortar`, `Projetos`, `Ajustes`), persisting user preferences via `QSettings` and project history in `output/projetos.json`.
- **Secondary surface:** Local web studio (`site/index.html`, `site/server.py`, currently listed in `.gitignore`) running over a local Python HTTP server against the same `core.pipeline` engine, storing browser preferences in `localStorage`.
- **Runtime environment:** Windows workstation with `ffmpeg` and `ffprobe` on `PATH`, local `faster-whisper` inference (`device="auto"` with CUDA/CPU support), and AI provider keys loaded from `.env` or environment variables.
- **Platform schema note:** `## Platform` is recorded as `web` to satisfy Impeccable's schema (`web`, `ios`, `android`, `adaptive`) and support `site/`, while the primary product runtime is the Windows `PySide6` desktop app.

## Capabilities and Constraints

- **Confirmed capabilities:**
  - Input via YouTube URL (`yt-dlp`) or local video file.
  - Audio extraction and cached transcription (`faster-whisper` with `.cache/` / `transcript.json` reuse).
  - Multi-provider AI analysis (`OpenRouter`, `Groq`, `Cerebras`, `Mistral`, `Google AI Studio`, `OpenAI`, `Ollama`) with automatic key/model rotation and structured JSON clip output.
  - 9:16 vertical rendering with blurred background, hardware encoder probing (`h264_nvenc`, `h264_qsv`, `h264_amf`, fallback `libx264`), and cooperative cancellation (`cancel_event`).
  - Dynamic `.ass` word-level captions with viral presets (`core/captions/presets.py`) and live 9:16 preview.
  - JSON/CSV clip reports (`relatorio.json`, `relatorio.csv`), local project accordion history, published toggles, and quick shortcuts to YouTube/TikTok upload pages.
- **Binding constraints:**
  - 100% local processing and state: no user accounts, cloud storage, remote backend, or subscription billing.
  - Primary interface copy and workflows in Brazilian Portuguese (`PT-BR`).
  - AI API keys are currently supplied via `.env` / environment variables rather than an in-app credential screen.
- **Explicitly undecided:**
  - Standalone Windows executable packaging format (`.exe` vs running directly via Python).
  - Long-term repository status and scope of `site/` relative to the primary desktop app.

## Brand Commitments

- **Name:** `AutoCortesBR` (styled as `autocortes.BR` in the web studio).
- **Language and tone:** Brazilian Portuguese (`PT-BR`), direct, practical, and creator-focused without marketing fluff.

## Evidence on Hand

- Working PySide6 desktop app (`main.py`, `gui/main_window.py`, `gui/settings_dialog.py`, `gui/projects_dialog.py`, `gui/widgets.py`, `gui/theme.py`).
- Working core pipeline and provider rotation (`core/pipeline.py`, `core/ai_analyzer.py`, `core/render.py`, `core/captions/`, `core/providers/`).
- Working secondary web studio (`site/index.html`, `site/server.py`, `site/README.md`).
- Automated test suite (`tests/`).
- Built-in viral caption preset catalog (`core/captions/presets.py`) and planning docs (`_plano_structure.md`, `_plano_captions.md`, `_plano_transicao.md`).
- **Absences:** No external customer testimonials, usage analytics, or public performance benchmarks exist; future work must not fabricate them.

## Product Principles

- **Local-first, zero lock-in:** Keep media, transcription, project history, and preferences under the user's local control with no SaaS dependencies.
- **Fast path from raw video to upload:** Favor sensible defaults, transcript caching, hardware-accelerated rendering, and one-click presets over manual setup friction.
- **Resilient execution:** Handle API rate limits/outages via multi-provider fallback and allow clean cancellation with temporary-file cleanup.
- **Practical clarity:** Use straightforward PT-BR labels and live previews so creators understand clip and caption outcomes before rendering.
