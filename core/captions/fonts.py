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

# Fontes que acompanham o app (assets/fonts, licenca OFL). Sao indexadas
# antes das do sistema e copiadas para a pasta do libass na renderizacao.
BUNDLED_FONTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets",
    "fonts",
)


def bundled_font_files() -> list[str]:
    if not os.path.isdir(BUNDLED_FONTS_DIR):
        return []
    return sorted(
        os.path.join(BUNDLED_FONTS_DIR, name)
        for name in os.listdir(BUNDLED_FONTS_DIR)
        if name.lower().endswith((".ttf", ".otf"))
    )


# Melhores fontes para legendas dinamicas em video vertical (exibidas no topo
# como "Recomendadas"). Fontes comerciais da lista aparecem automaticamente caso
# estejam instaladas no sistema; equivalentes/originais OFL ficam em assets/fonts.
RECOMMENDED_FONTS = [
    # Sans-Serif Geométricas e Neutras
    "Helvetica",
    "Helvetica Neue",
    "Univers",
    "Inter",
    "Montserrat",
    "Poppins",
    "Futura",
    "Nexa",
    "Mont",
    "Gotham",
    "Lato",
    "Fira Sans",
    "Trebuchet MS",
    "Tahoma",
    # Sans-Serif Condensadas (alto impacto)
    "Bebas Neue",
    "Postamp Grotesk",
    "Intro",
    "Impact",
    "Bahnschrift",
    # Serifadas (elegância e estilo editorial)
    "Garamond",
    "EB Garamond",
    "Bodoni",
    "Bodoni Moda",
]

PRECONFIGURED_FONTS = [
    "Poppins",
    "Montserrat",
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
    BUNDLED_FONTS_DIR,
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
                italic = "italic" in style_l or "oblique" in style_l
                key = family.strip().lower()
                if not key:
                    continue
                slot = index.setdefault(key, {})
                is_bold = any(
                    tag in style_l for tag in ("bold", "black", "heavy", "demi")
                )
                kind = ("bold" if is_bold else "regular") + (
                    "_italic" if italic else ""
                )
                # "Bold" exato vence variantes (ExtraBold, Black...)
                exact = style_l.replace("italic", "").strip() in ("bold", "regular", "")
                if exact:
                    slot[f"_{kind}_exact"] = slot.get(f"_{kind}_exact") or fpath
                slot.setdefault(kind, fpath)
                if not italic:
                    display_names.setdefault(key, family.strip())

    for slot in index.values():
        for kind in ("regular", "bold", "regular_italic", "bold_italic"):
            exact = slot.pop(f"_{kind}_exact", None)
            if exact:
                slot[kind] = exact
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


def find_font_path(
    font_name: str = "Arial", bold: bool = True, italic: bool = False
) -> str | None:
    """Localiza um .ttf concreto para uso no PIL e no libass."""
    name = (font_name or "Arial").strip()
    slug = name.lower().replace(" ", "")
    win = "C:/Windows/Fonts/"
    if italic:
        entry = build_font_index().get(name.lower()) or {}
        order = ("bold_italic", "regular_italic") if bold else ("regular_italic", "bold_italic")
        for kind in order:
            chosen = entry.get(kind)
            if chosen and os.path.exists(chosen):
                return chosen
        for path in (
            [f"{win}{slug}bi.ttf", f"{win}{slug}z.ttf"] if bold else [f"{win}{slug}i.ttf"]
        ):
            if os.path.exists(path):
                return path
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


def libass_scale(path: str) -> float:
    """Fracao do `Fontsize` que o libass usa como em: ele dimensiona pela
    altura ascent+descent da fonte (Arial ~0.89, Poppins ~0.71)."""
    if os.getenv("CAPTION_FONT_SCALE"):
        return _LIBASS_FONT_SCALE
    metrics = _win_metrics(path)
    if metrics:
        units, height = metrics
        return max(0.4, min(1.0, units / float(height)))
    try:
        ascent, descent = ImageFont.truetype(path, 1000).getmetrics()
        return max(0.4, min(1.0, 1000.0 / float(ascent + descent)))
    except Exception:
        return _LIBASS_FONT_SCALE


def _win_metrics(path: str) -> tuple[int, int] | None:
    """(unitsPerEm, usWinAscent+usWinDescent) lidos direto do .ttf/.otf."""
    import struct

    try:
        with open(path, "rb") as fh:
            data = fh.read()
        num_tables = struct.unpack(">H", data[4:6])[0]
        tables = {}
        for i in range(num_tables):
            rec = data[12 + 16 * i : 28 + 16 * i]
            tag = rec[:4].decode("latin-1")
            offset = struct.unpack(">I", rec[8:12])[0]
            tables[tag] = offset
        units = struct.unpack(">H", data[tables["head"] + 18 : tables["head"] + 20])[0]
        os2 = tables["OS/2"]
        win_ascent, win_descent = struct.unpack(">HH", data[os2 + 74 : os2 + 78])
        if units and win_ascent + win_descent:
            return units, win_ascent + win_descent
    except Exception:
        return None
    return None


def font_effective_size(font, size: float) -> float:
    scale = getattr(font, "libass_scale", None) or _LIBASS_FONT_SCALE
    return max(1.0, float(size) * scale)


def load_font(font_name: str, bold: bool, size: int, italic: bool = False):
    """Retorna (font PIL, familia, bold, pasta da fonte)."""
    path = find_font_path(font_name, bold, italic)
    if path:
        scale = libass_scale(path)
        font = ImageFont.truetype(path, max(1, round(size * scale)))
        font.libass_scale = scale
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



def register_bundled_fonts() -> int:
    """Disponibiliza as fontes do app para o Qt (previas e lista de fontes),
    sem precisar instala-las no sistema. Retorna quantas foram registradas."""
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:
        return 0
    count = 0
    for path in bundled_font_files():
        if QFontDatabase.addApplicationFont(path) >= 0:
            count += 1
    return count
