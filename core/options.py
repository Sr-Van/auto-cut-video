"""Opcoes de processamento configuraveis em tempo de execucao.

Centraliza o que antes eram constantes do modulo `core.config`, permitindo
que o GUI (ou o CLI) ajuste video vertical, legendas e parametros de IA sem
mexer em env vars. `ProcessingOptions` atua como unica fonte de verdade
durante a execucao do pipeline.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from core import config as cfg


@dataclass
class ProcessingOptions:
    # --- Video vertical 9:16 ---
    vertical_enabled: bool = cfg.VERTICAL_ENABLED
    width: int = cfg.VERTICAL_WIDTH
    height: int = cfg.VERTICAL_HEIGHT
    zoom: float = cfg.VERTICAL_ZOOM
    blur_sigma: float = cfg.VERTICAL_BLUR_SIGMA
    blur_divisor: int = cfg.VERTICAL_BLUR_DIVISOR
    bg_brightness: float = cfg.VERTICAL_BG_BRIGHTNESS
    encoder: str = cfg.VERTICAL_ENCODER
    crf: int = cfg.VERTICAL_CRF
    preset: str = cfg.VERTICAL_PRESET
    max_workers: int = cfg.VERTICAL_MAX_WORKERS
    padding_s: float = float(cfg.PADDING_S)

    # --- Legendas dinamicas ---
    captions_enabled: bool = False
    caption_font: str = "Arial"
    caption_bold: bool = True
    caption_font_size: int = 72
    caption_text_color: str = "#FFFFFF"
    caption_highlight_color: str = "#7C3AED"
    caption_highlight_opacity: float = 1.0
    caption_box_padding: int = 14
    caption_corner_radius: int = 22
    # Multiplicador sobre o avanco do espaco da fonte (1.0 = natural).
    caption_word_spacing: float = 1.0
    caption_outline_color: str = "#000000"
    caption_outline_width: int = 3
    caption_uppercase: bool = False
    caption_max_words_per_line: int = 4
    caption_max_lines: int = 2
    caption_max_block_duration: float = 3.0
    caption_gap_break: float = 0.7
    # Margem a partir do rodape (em px do canvas). Valores altos caem na
    # faixa desfocada embaixo do video principal.
    caption_margin_bottom: int = 300
    # "full" = usa a transcricao geral (com palavras); "clip" = retranscreve
    # cada clipe (mais preciso, so faz sentido com GPU).
    caption_transcribe_mode: str = "clip"

    # --- Cortes & IA ---
    max_clips: int = cfg.MAX_CLIPS
    min_viral_score: int = cfg.MIN_VIRAL_SCORE
    min_clip_duration: int = cfg.MIN_CLIP_DURATION
    max_clip_duration: int = cfg.MAX_CLIP_DURATION
    pause_gap: float = float(cfg.PAUSE_GAP)
    whisper_model: str = cfg.WHISPER_MODEL
    whisper_compute_type: str = cfg.WHISPER_COMPUTE_TYPE
    language: str = cfg.LANGUAGE
    # Instrucao livre do usuario sobre em que focar (vira "REGRA EXTRA" no prompt).
    focus_instruction: str = ""

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> "ProcessingOptions":
        """Garante consistencia e aplica fallbacks de `core.config` quando necessario."""
        self.whisper_model = (
            str(self.whisper_model or "").strip() or cfg.WHISPER_MODEL
        )
        self.whisper_compute_type = (
            str(self.whisper_compute_type or "").strip()
            or cfg.WHISPER_COMPUTE_TYPE
        )
        self.language = str(self.language or "").strip() or cfg.LANGUAGE
        self.min_clip_duration = max(
            1, int(self.min_clip_duration or cfg.MIN_CLIP_DURATION)
        )
        self.max_clip_duration = max(
            self.min_clip_duration,
            int(self.max_clip_duration or cfg.MAX_CLIP_DURATION),
        )
        self.pause_gap = float(
            self.pause_gap if self.pause_gap is not None else cfg.PAUSE_GAP
        )
        self.max_clips = max(1, int(self.max_clips or cfg.MAX_CLIPS))
        self.min_viral_score = max(
            0,
            min(
                10,
                int(
                    self.min_viral_score
                    if self.min_viral_score is not None
                    else cfg.MIN_VIRAL_SCORE
                ),
            ),
        )
        self.focus_instruction = str(self.focus_instruction or "").strip()
        return self

    @classmethod
    def from_env_or_config(cls, **overrides) -> "ProcessingOptions":
        """Constroi `ProcessingOptions` carregando todos os defaults de `core.config`."""
        opts = cls(
            vertical_enabled=cfg.VERTICAL_ENABLED,
            width=cfg.VERTICAL_WIDTH,
            height=cfg.VERTICAL_HEIGHT,
            zoom=cfg.VERTICAL_ZOOM,
            blur_sigma=cfg.VERTICAL_BLUR_SIGMA,
            blur_divisor=cfg.VERTICAL_BLUR_DIVISOR,
            bg_brightness=cfg.VERTICAL_BG_BRIGHTNESS,
            encoder=cfg.VERTICAL_ENCODER,
            crf=cfg.VERTICAL_CRF,
            preset=cfg.VERTICAL_PRESET,
            max_workers=cfg.VERTICAL_MAX_WORKERS,
            padding_s=float(cfg.PADDING_S),
            max_clips=cfg.MAX_CLIPS,
            min_viral_score=cfg.MIN_VIRAL_SCORE,
            min_clip_duration=cfg.MIN_CLIP_DURATION,
            max_clip_duration=cfg.MAX_CLIP_DURATION,
            pause_gap=float(cfg.PAUSE_GAP),
            whisper_model=cfg.WHISPER_MODEL,
            whisper_compute_type=cfg.WHISPER_COMPUTE_TYPE,
            language=cfg.LANGUAGE,
        )
        if overrides:
            return cls.from_dict({**opts.to_dict(), **overrides})
        return opts.normalize()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "ProcessingOptions":
        opts = cls()
        if not data:
            return opts
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in known or value is None:
                continue
            current = getattr(opts, key)
            try:
                if isinstance(current, bool):
                    if isinstance(value, bool):
                        cast = value
                    else:
                        cast = str(value).strip().lower() in (
                            "1",
                            "true",
                            "yes",
                            "on",
                        )
                elif isinstance(current, int):
                    cast = int(float(value))
                elif isinstance(current, float):
                    cast = float(value)
                else:
                    cast = str(value)
            except (TypeError, ValueError):
                continue
            setattr(opts, key, cast)
        return opts.normalize()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw) -> "ProcessingOptions":
        if not raw:
            return cls.from_env_or_config()
        if isinstance(raw, dict):
            return cls.from_dict(raw)
        try:
            return cls.from_dict(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return cls.from_env_or_config()
