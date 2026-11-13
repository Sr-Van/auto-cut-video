"""Modelos de dados para legendas dinamicas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaptionWord:
    start: float
    end: float
    text: str
    x: float = 0.0
    y: float = 0.0
    # Preenchidos pelo layout: largura medida (ja com escala) e enfase.
    width: float = 0.0
    scale: float = 1.0
    emphasis: bool = False


@dataclass
class CaptionBlock:
    start: float
    end: float
    words: list[CaptionWord] = field(default_factory=list)

