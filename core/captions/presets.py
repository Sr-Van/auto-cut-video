"""Catalogo de Presets de Legendas Virais e funcoes de aplicacao/deteccao."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.options import ProcessingOptions


@dataclass(frozen=True)
class CaptionPreset:
    id: str
    name: str
    tag: str
    description: str
    sample_text: str
    settings: dict[str, Any]


VIRAL_PRESETS: dict[str, CaptionPreset] = {
    "hormozi_bold": CaptionPreset(
        id="hormozi_bold",
        name="Hormozi Pop",
        tag="Impacto",
        description="Caixa alta, amarelo vibrante na palavra falada e contorno forte.",
        sample_text="CORTE VIRAL",
        settings={
            "caption_font": "Arial",
            "caption_bold": True,
            "caption_font_size": 74,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#FACC15",
            "caption_highlight_opacity": 0.0,
            "caption_box_padding": 12,
            "caption_corner_radius": 18,
            "caption_outline_color": "#000000",
            "caption_outline_width": 4,
            "caption_max_words_per_line": 3,
            "caption_max_lines": 2,
            "caption_margin_bottom": 380,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    "podcast_cabrini": CaptionPreset(
        id="podcast_cabrini",
        name="Podcast Gold",
        tag="Dinâmico",
        description="Destaque em verde lima neon, ideal para entrevistas e cortes de podcast.",
        sample_text="REVELAÇÃO",
        settings={
            "caption_font": "Arial",
            "caption_bold": True,
            "caption_font_size": 70,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#22C55E",
            "caption_highlight_opacity": 0.88,
            "caption_box_padding": 12,
            "caption_corner_radius": 18,
            "caption_outline_color": "#000000",
            "caption_outline_width": 3,
            "caption_max_words_per_line": 3,
            "caption_max_lines": 2,
            "caption_margin_bottom": 340,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    "tiktok_purple": CaptionPreset(
        id="tiktok_purple",
        name="TikTok Studio",
        tag="Padrão",
        description="Pílula roxa arredondada que corre e acompanha cada palavra.",
        sample_text="Destaque",
        settings={
            "caption_font": "Arial",
            "caption_bold": True,
            "caption_font_size": 72,
            "caption_uppercase": False,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#7C3AED",
            "caption_highlight_opacity": 1.0,
            "caption_box_padding": 14,
            "caption_corner_radius": 22,
            "caption_outline_color": "#000000",
            "caption_outline_width": 3,
            "caption_max_words_per_line": 4,
            "caption_max_lines": 2,
            "caption_margin_bottom": 300,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    "cyber_neon": CaptionPreset(
        id="cyber_neon",
        name="Cyber Neon",
        tag="Tech & Games",
        description="Contraste ciano neon vibrante em caixa alta para tecnologia e finanças.",
        sample_text="FUTURO IA",
        settings={
            "caption_font": "Trebuchet MS",
            "caption_bold": True,
            "caption_font_size": 70,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#06B6D4",
            "caption_highlight_opacity": 0.9,
            "caption_box_padding": 14,
            "caption_corner_radius": 20,
            "caption_outline_color": "#000000",
            "caption_outline_width": 3,
            "caption_max_words_per_line": 3,
            "caption_max_lines": 2,
            "caption_margin_bottom": 320,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    "stronda_impact": CaptionPreset(
        id="stronda_impact",
        name="Stronda Impact",
        tag="Rápido",
        description="Tipografia condensada no centro inferior, 1 a 2 palavras por vez.",
        sample_text="SEM DESCULPA",
        settings={
            "caption_font": "Impact",
            "caption_bold": True,
            "caption_font_size": 78,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#EAB308",
            "caption_highlight_opacity": 0.0,
            "caption_box_padding": 10,
            "caption_corner_radius": 14,
            "caption_outline_color": "#000000",
            "caption_outline_width": 4,
            "caption_max_words_per_line": 2,
            "caption_max_lines": 1,
            "caption_margin_bottom": 420,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    "stronda_rise": CaptionPreset(
        id="stronda_rise",
        name="Stronda Rise",
        tag="Subir & Revelar",
        description="Subida dinâmica palavra a palavra com contorno grosso (8px) e destaque amarelo.",
        sample_text="CORTE VIRAL",
        settings={
            "caption_font": "Impact",
            "caption_bold": True,
            "caption_font_size": 78,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#EAB308",
            "caption_highlight_opacity": 0.0,
            "caption_box_padding": 10,
            "caption_corner_radius": 14,
            "caption_outline_color": "#000000",
            "caption_outline_width": 8,
            "caption_max_words_per_line": 2,
            "caption_max_lines": 1,
            "caption_margin_bottom": 420,
            "caption_animation": "rise",
            "caption_glow": False,
        },
    ),
    "impact_glow": CaptionPreset(
        id="impact_glow",
        name="Impact Glow",
        tag="White Glow",
        description="Texto bold branco com subida suave, contorno cinza gelo (1px) e halo glow suave.",
        sample_text="CORTE VIRAL",
        settings={
            "caption_font": "Impact",
            "caption_bold": True,
            "caption_font_size": 78,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#FFFFFF",
            "caption_highlight_opacity": 0.0,
            "caption_box_padding": 10,
            "caption_corner_radius": 14,
            "caption_outline_color": "#CBD5E1",
            "caption_outline_width": 1,
            "caption_max_words_per_line": 2,
            "caption_max_lines": 1,
            "caption_margin_bottom": 420,
            "caption_animation": "rise",
            "caption_glow": True,
        },
    ),
    "stronda_red_box": CaptionPreset(
        id="stronda_red_box",
        name="Stronda Red Box",
        tag="Bloco Rápido",
        description="Ritmo rápido (até 2 palavras) em caixa alta com pílula vermelha animada na palavra atual.",
        sample_text="SEM DESCULPA",
        settings={
            "caption_font": "Impact",
            "caption_bold": True,
            "caption_font_size": 78,
            "caption_uppercase": True,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#EF4444",
            "caption_highlight_opacity": 1.0,
            "caption_box_padding": 14,
            "caption_corner_radius": 22,
            "caption_outline_color": "#000000",
            "caption_outline_width": 3,
            "caption_max_words_per_line": 2,
            "caption_max_lines": 1,
            "caption_margin_bottom": 420,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    "clean_minimal": CaptionPreset(
        id="clean_minimal",
        name="Clean Minimal",
        tag="Discreto",
        description="Legenda limpa sem caixas coloridas, ideal para relatos e documentários.",
        sample_text="História real",
        settings={
            "caption_font": "Segoe UI",
            "caption_bold": True,
            "caption_font_size": 64,
            "caption_uppercase": False,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#E5E7EB",
            "caption_highlight_opacity": 0.0,
            "caption_box_padding": 10,
            "caption_corner_radius": 14,
            "caption_outline_color": "#111827",
            "caption_outline_width": 2,
            "caption_max_words_per_line": 4,
            "caption_max_lines": 2,
            "caption_margin_bottom": 280,
            "caption_animation": "pop",
            "caption_glow": False,
        },
    ),
    # --- Inspirados nos shorts de referencia (CapCut) ---
    "capcut_revelado": CaptionPreset(
        id="capcut_revelado",
        name="Karaokê Revelado",
        tag="CapCut",
        description="Bloco em Poppins itálico: cada palavra cai de cima quando é falada; palavra em foco em amarelo, com glow suave ao fundo.",
        sample_text="o povo quer saber",
        settings={
            "caption_font": "Poppins",
            "caption_bold": True,
            "caption_italic": True,
            "caption_font_size": 82,
            "caption_uppercase": False,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#FFFFFF",
            "caption_highlight_opacity": 0.0,
            "caption_outline_color": "#000000",
            "caption_outline_width": 0,
            "caption_shadow": 2,
            "caption_karaoke_mode": "cumulative",
            "caption_upcoming_color": "#FFFFFF",
            "caption_upcoming_opacity": 0.0,
            "caption_emphasis": True,
            "caption_emphasis_color": "#FACC15",
            "caption_emphasis_scale": 1.0,
            "caption_glow": True,
            "caption_glow_color": "#000000",
            "caption_glow_strength": 12,
            "caption_max_words_per_line": 3,
            "caption_max_lines": 2,
            "caption_margin_bottom": 640,
            "caption_animation": "drop",
        },
    ),
    "capcut_glow_word": CaptionPreset(
        id="capcut_glow_word",
        name="Palavra Glow",
        tag="CapCut",
        description="Uma palavra por vez, grande, branca com halo difuso e entrada com borrão.",
        sample_text="celular",
        settings={
            "caption_font": "Montserrat",
            "caption_bold": True,
            "caption_font_size": 132,
            "caption_uppercase": False,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#FFFFFF",
            "caption_highlight_opacity": 0.0,
            "caption_outline_color": "#FFFFFF",
            "caption_outline_width": 0,
            "caption_shadow": 0,
            "caption_max_words_per_line": 1,
            "caption_max_lines": 1,
            "caption_margin_bottom": 560,
            "caption_animation": "blur_in",
            "caption_glow": True,
            "caption_glow_color": "#FFFFFF",
            "caption_glow_strength": 14,
        },
    ),
    "capcut_keyword": CaptionPreset(
        id="capcut_keyword",
        name="Palavra-chave",
        tag="CapCut",
        description="Composição em escada (até 4 palavras por cena): conteúdo grande, apoio pequeno no topo, última palavra-chave colorida; cada palavra sobe ganhando opacidade.",
        sample_text="me chama no WhatsApp",
        settings={
            "caption_font": "Montserrat",
            "caption_bold": True,
            "caption_font_size": 50,
            "caption_uppercase": False,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#FFFFFF",
            "caption_highlight_opacity": 0.0,
            "caption_outline_color": "#000000",
            "caption_outline_width": 2,
            "caption_shadow": 5,
            "caption_emphasis": True,
            "caption_emphasis_color": "#2F6BFF",
            "caption_emphasis_scale": 2.3,
            "caption_layout": "stairs",
            "caption_max_words_per_line": 4,
            "caption_max_lines": 1,
            "caption_margin_bottom": 640,
            "caption_animation": "rise",
            "caption_glow": False,
        },
    ),
    "capcut_keyword_neon": CaptionPreset(
        id="capcut_keyword_neon",
        name="Destaque Neon",
        tag="CapCut",
        description="Palavras de apoio pequenas e a palavra-chave grande em roxo neon com brilho.",
        sample_text="você teria coragem",
        settings={
            "caption_font": "Poppins",
            "caption_bold": True,
            "caption_font_size": 70,
            "caption_uppercase": False,
            "caption_text_color": "#FFFFFF",
            "caption_highlight_color": "#FFFFFF",
            "caption_highlight_opacity": 0.0,
            "caption_outline_color": "#000000",
            "caption_outline_width": 0,
            "caption_shadow": 3,
            "caption_emphasis": True,
            "caption_emphasis_color": "#A855F7",
            "caption_emphasis_scale": 1.6,
            "caption_glow": True,
            "caption_glow_color": "#A855F7",
            "caption_glow_strength": 10,
            "caption_max_words_per_line": 3,
            "caption_max_lines": 2,
            "caption_margin_bottom": 640,
            "caption_animation": "pop",
        },
    ),
}

# Campos de estilo que nem todo preset define: voltam ao padrao ao trocar de
# preset, para um preset novo (ex.: karaoke) nao "vazar" para o seguinte.
STYLE_DEFAULTS: dict[str, Any] = {
    "caption_italic": False,
    "caption_shadow": 1,
    "caption_karaoke_mode": "active",
    "caption_layout": "line",
    "caption_upcoming_color": "#FFFFFF",
    "caption_upcoming_opacity": 1.0,
    "caption_emphasis": False,
    "caption_emphasis_color": "#22C55E",
    "caption_emphasis_scale": 1.0,
    "caption_glow_color": "#FFFFFF",
    "caption_glow_strength": 6,
}


def preset_settings(preset: CaptionPreset) -> dict[str, Any]:
    return {**STYLE_DEFAULTS, **preset.settings}

# Compatibilidade legada com dict simples de cores
PRESETS: dict[str, tuple[str, str]] = {
    preset.name: (
        preset.settings["caption_highlight_color"],
        preset.settings["caption_text_color"],
    )
    for preset in VIRAL_PRESETS.values()
}


def apply_preset(options: ProcessingOptions, preset_id: str) -> ProcessingOptions:
    """Aplica os valores de um preset viral sobre uma instancia de `ProcessingOptions`."""
    if preset_id == "stronda_swing" and "stronda_swing" not in VIRAL_PRESETS:
        preset_id = "stronda_rise"
    preset = VIRAL_PRESETS.get(preset_id)
    if preset is None:
        # Tenta buscar pelo nome exibido
        for candidate in VIRAL_PRESETS.values():
            if candidate.name.lower() == (preset_id or "").strip().lower():
                preset = candidate
                break
    if preset is None:
        return options

    for attr, value in preset_settings(preset).items():
        if hasattr(options, attr):
            setattr(options, attr, value)
    return options


def detect_active_preset(options: ProcessingOptions) -> str | None:
    """Retorna o ID do preset cujas configuracoes coincidem com `options`, ou None se personalizado."""
    for preset_id, preset in VIRAL_PRESETS.items():
        matched = True
        for key, expected in preset_settings(preset).items():
            actual = getattr(options, key, None)
            if isinstance(expected, float):
                if actual is None or abs(float(actual) - expected) > 0.02:
                    matched = False
                    break
            elif isinstance(expected, str):
                if str(actual or "").strip().lower() != expected.strip().lower():
                    matched = False
                    break
            else:
                if actual != expected:
                    matched = False
                    break
        if matched:
            return preset_id
    return None

