"""Descoberta, indexacao e resolucao de fontes .ttf/.otf do sistema."""

from __future__ import annotations

import os

from PIL import ImageFont

# O libass deste build renderiza a fonte a ~90% do `Fontsize` informado no ASS
# (constante de 36 a 144px). O PIL precisa medir na MESMA escala, senao as
# palavras ficam mais afastadas que o normal. Ajustavel por env, se o FFmpeg
# mudar de comportamento.
_LIBASS_FONT_SCALE = float(os.getenv("CAPTION_FONT_SCALE", "0.9"))


def effective_size(size: float) -> float:
    return max(1.0, float(size) * _LIBASS_FONT_SCALE)


_FALLBACK_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

PRECONFIGURED_FONTS = [
    "Arial",
    "Segoe UI",
    "Verdana",
    "Tahoma",
    "Trebuchet MS",
    "Impact",
    "Calibri",
    "Consolas",
    "Georgia",
    "DejaVu Sans",
]

_FONT_DIRS = [
    "C:/Windows/Fonts",
    os.path.expandvars(r"%LOCALAPPDATA%/Microsoft/Windows/Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/System/Library/Fonts",
    "/Library/Fonts",
]

_FONT_INDEX: dict[str, dict[str, str]] | None = None
_SYSTEM_FONT_NAMES: list[str] | None = None


def build_font_index() -> dict[str, dict[str, str]]:
    """Indexa as famílias .ttf/.otf instaladas no computador (regular e bold)."""
    global _FONT_INDEX, _SYSTEM_FONT_NAMES
    if _FONT_INDEX is not None:
        return _FONT_INDEX

    index: dict[str, dict[str, str]] = {}
    display_names: dict[str, str] = {}

    for folder in _FONT_DIRS:
        if not folder or not os.path.isdir(folder):
            continue
        try:
            walker = os.walk(folder)
        except OSError:
            continue
        for root, _dirs, files in walker:
            for fname in files:
                if not fname.lower().endswith((".ttf", ".otf")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    font = ImageFont.truetype(fpath, 16)
                    family, style = font.getname()
                except Exception:
                    continue
                if not family or family.startswith("@"):
                    continue
                style_l = (style or "").lower()
                if "italic" in style_l or "oblique" in style_l:
                    continue
                key = family.strip().lower()
                if not key:
                    continue
                display_names.setdefault(key, family.strip())
                slot = index.setdefault(key, {})
                is_bold = any(
                    tag in style_l for tag in ("bold", "black", "heavy", "demi")
                )
                if is_bold:
                    slot.setdefault("bold", fpath)
                else:
                    slot.setdefault("regular", fpath)

    _FONT_INDEX = index
    _SYSTEM_FONT_NAMES = sorted(display_names.values(), key=str.casefold)
    return index


def list_available_fonts() -> list[str]:
    """Retorna as fontes pré-configuradas seguidas das demais fontes do sistema."""
    build_font_index()
    system_names = _SYSTEM_FONT_NAMES or []
    seen: set[str] = set()
    ordered: list[str] = []

    for name in PRECONFIGURED_FONTS:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(name)

    for name in system_names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(name)

    return ordered


def find_font_path(font_name: str = "Arial", bold: bool = True) -> str | None:
    """Localiza um .ttf concreto para uso no PIL e no libass."""
    name = (font_name or "Arial").strip()
    slug = name.lower().replace(" ", "")
    win = "C:/Windows/Fonts/"
    candidates: list[str] = []
    if bold:
        candidates += [
            f"{win}{slug}bd.ttf",
            f"{win}{slug}b.ttf",
            f"{win}{slug} bold.ttf",
        ]
    candidates.append(f"{win}{slug}.ttf")
    for path in candidates:
        if os.path.exists(path):
            return path

    index = build_font_index()
    entry = index.get(name.lower())
    if entry:
        chosen = (
            entry.get("bold") or entry.get("regular")
            if bold
            else entry.get("regular") or entry.get("bold")
        )
        if chosen and os.path.exists(chosen):
            return chosen

    for path in _FALLBACK_FONTS:
        if os.path.exists(path):
            return path
    return None


def load_font(font_name: str, bold: bool, size: int):
    """Retorna (font PIL, familia, bold, pasta da fonte)."""
    path = find_font_path(font_name, bold)
    if path:
        font = ImageFont.truetype(path, round(effective_size(size)))
        try:
            family, style = font.getname()
        except Exception:
            family, style = font_name, "Bold" if bold else "Regular"
        return (
            font,
            family,
            "bold" in (style or "").lower() or bold,
            os.path.dirname(path),
        )
    return ImageFont.load_default(), font_name, bold, None

