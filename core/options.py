"""Opcoes de processamento configuraveis em tempo de execucao.

Centraliza o que antes eram constantes do modulo `core.config`, permitindo
que o GUI (ou o CLI) ajuste video vertical e legendas sem mexer em env vars.
Os defaults continuam vindo do `core.config`, entao o comportamento atual
e preservado se nada for informado.
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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "ProcessingOptions":
        opts = cls()
        if not data:
            return opts
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in known:
                continue
            current = getattr(opts, key)
            try:
                if isinstance(current, bool):
                    if isinstance(value, bool):
                        cast = value
                    else:
                        cast = str(value).strip().lower() in ("1", "true", "yes", "on")
                elif isinstance(current, int):
                    cast = int(float(value))
                elif isinstance(current, float):
                    cast = float(value)
                else:
                    cast = str(value)
            except (TypeError, ValueError):
                continue
            setattr(opts, key, cast)
        return opts

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw) -> "ProcessingOptions":
        if not raw:
            return cls()
        if isinstance(raw, dict):
            return cls.from_dict(raw)
        try:
            return cls.from_dict(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return cls()
