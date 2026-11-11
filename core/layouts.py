"""Catalogo de formatos de short (layouts 9:16).

Cada formato e uma pilha vertical de *slots*. O usuario escolhe o formato
antes de processar (fica salvo nas opcoes), entao o pipeline nao precisa
adivinhar: so localiza o que cada slot pede (rosto, webcam, conteudo) e
monta tudo em um unico `filter_complex` do FFmpeg.

Tipos de slot:
- video   : o corte inteiro (contain + zoom do slot) sobre fundo desfocado
- focus   : recorte que segue o rosto de quem fala (fallback: centro)
- cam     : recorte da webcam detectada num canto (react)
- content : o video sem a regiao da webcam (react)
- text    : faixa com texto (gancho/titulo da IA ou texto fixo)
- image   : imagem auxiliar enviada pelo usuario
"""

from __future__ import annotations

from dataclasses import dataclass, field

SLOT_KINDS = ("video", "focus", "cam", "content", "text", "image")
VISION_SLOTS = {"focus", "cam", "content"}


@dataclass(frozen=True)
class Slot:
    kind: str
    height: float  # fracao da altura total (a soma do layout e 1.0)
    zoom: float = 1.0  # so para `video`: zoom sobre o contain
    fit: str = "contain"  # `video`: "contain" (fundo desfocado) ou "cover" (zoom ate preencher)


@dataclass(frozen=True)
class Layout:
    id: str
    name: str
    tag: str
    description: str
    slots: tuple[Slot, ...]
    requires: frozenset = field(default_factory=frozenset)  # {"image"}
    legacy: bool = False  # usa o filtro classico (fundo desfocado + zoom global)
    # Legenda: em qual slot fica, onde fica a base do bloco dentro dele
    # (0 = topo do slot, 1 = base) e escala sobre o tamanho do preset.
    caption_slot: int = 0
    caption_anchor: float = 0.82
    caption_scale: float = 1.0

    @property
    def needs_vision(self) -> bool:
        return any(s.kind in VISION_SLOTS for s in self.slots)

    @property
    def has_text(self) -> bool:
        return any(s.kind == "text" for s in self.slots)

    @property
    def has_image(self) -> bool:
        return any(s.kind == "image" for s in self.slots)


LAYOUTS: dict[str, Layout] = {
    "center": Layout(
        id="center",
        name="Centralizado",
        tag="Clássico",
        description="Vídeo inteiro no centro com fundo desfocado. Bom para uma pessoa só.",
        slots=(Slot("video", 1.0),),
        legacy=True,
        caption_slot=0, caption_anchor=0.68, caption_scale=1.15,
    ),
    "follow": Layout(
        id="follow",
        name="Seguir quem fala",
        tag="Podcast",
        description="Tela cheia no rosto de quem está falando; troca de pessoa sozinho.",
        slots=(Slot("focus", 1.0),),
        caption_slot=0, caption_anchor=0.7, caption_scale=1.1,
    ),
    "react": Layout(
        id="react",
        name="React split",
        tag="React",
        description="Conteúdo em cima e a webcam do streamer ampliada embaixo.",
        slots=(Slot("content", 0.58), Slot("cam", 0.42)),
        caption_slot=1, caption_anchor=0.93, caption_scale=0.75,
    ),
    "title_middle": Layout(
        id="title_middle",
        name="Título no meio",
        tag="Gancho",
        description="Rosto em cima, faixa com o gancho no meio e o vídeo inteiro embaixo.",
        slots=(Slot("focus", 0.44), Slot("text", 0.14), Slot("video", 0.42, 1.0, "cover")),
        caption_slot=2, caption_anchor=0.95, caption_scale=0.9,
    ),
    "image_video": Layout(
        id="image_video",
        name="Imagem + vídeo",
        tag="Auxiliar",
        description="Sua imagem em cima, faixa de texto e o vídeo embaixo.",
        slots=(Slot("image", 0.38), Slot("text", 0.14), Slot("video", 0.48, 1.0, "cover")),
        requires=frozenset({"image"}),
        caption_slot=2, caption_anchor=0.96, caption_scale=0.9,
    ),
}

DEFAULT_LAYOUT_ID = "center"
TEXT_SOURCES = ("hook", "title", "custom")


def get_layout(layout_id: str | None) -> Layout:
    return LAYOUTS.get(str(layout_id or "").strip(), LAYOUTS[DEFAULT_LAYOUT_ID])


def slot_heights(layout: Layout, total_height: int) -> list[int]:
    """Alturas em px, todas pares, somando exatamente `total_height`."""
    heights: list[int] = []
    used = 0
    for i, slot in enumerate(layout.slots):
        if i == len(layout.slots) - 1:
            h = total_height - used
        else:
            h = max(2, int(round(total_height * slot.height / 2)) * 2)
        heights.append(h)
        used += h
    return heights


def caption_options(options):
    """Copia das opcoes com tamanho e posicao da legenda ajustados ao formato.

    O preset de legenda define o estilo; o formato decide onde a legenda cabe
    sem cobrir o que importa (rosto, webcam, faixa de texto, imagem).
    """
    from core.options import ProcessingOptions

    layout = get_layout(getattr(options, "layout_id", DEFAULT_LAYOUT_ID))
    adjusted = ProcessingOptions.from_dict(options.to_dict())
    heights = slot_heights(layout, int(options.height))
    index = max(0, min(len(heights) - 1, layout.caption_slot))
    slot_top = sum(heights[:index])
    bottom = slot_top + heights[index] * max(0.05, min(1.0, layout.caption_anchor))
    # escala tambem pela resolucao (presets foram pensados em 1080 de largura)
    res_scale = int(options.width) / 1080.0
    adjusted.caption_font_size = max(
        18, int(round(options.caption_font_size * layout.caption_scale * res_scale))
    )
    adjusted.caption_margin_bottom = max(0, int(round(options.height - bottom)))
    return adjusted


def missing_requirements(layout: Layout, image_path: str = "") -> list[str]:
    """Lista legivel do que falta para o formato funcionar."""
    from pathlib import Path

    missing = []
    if "image" in layout.requires and not (image_path and Path(image_path).is_file()):
        missing.append(f"O formato '{layout.name}' precisa de uma imagem auxiliar.")
    return missing


def clip_band_text(clip: dict, source: str, custom: str = "") -> str:
    """Texto da faixa para um corte, conforme a fonte escolhida."""
    source = source if source in TEXT_SOURCES else "hook"
    if source == "custom" and custom.strip():
        return custom.strip()
    if source == "title":
        return str(clip.get("title") or clip.get("hook_text") or "").strip()
    return str(clip.get("hook_text") or clip.get("title") or "").strip()
