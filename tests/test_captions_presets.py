import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.captions import (
    PRESETS,
    VIRAL_PRESETS,
    CaptionBlock,
    CaptionPreset,
    CaptionWord,
    apply_preset,
    build_ass,
    detect_active_preset,
    find_font_path,
    list_available_fonts,
    write_ass,
)
from core.options import ProcessingOptions
from gui.settings_dialog import SettingsDialog
from gui.widgets import CollapsibleBox, PhonePreviewWidget, PresetGrid


class TestCaptionsPresets(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_viral_presets_catalog(self) -> None:
        expected_ids = {
            "hormozi_bold",
            "podcast_cabrini",
            "tiktok_purple",
            "cyber_neon",
            "stronda_impact",
            "stronda_rise",
            "impact_glow",
            "stronda_red_box",
            "clean_minimal",
        }
        self.assertEqual(set(VIRAL_PRESETS.keys()), expected_ids)
        self.assertEqual(len(PRESETS), 9)

        for preset_id, preset in VIRAL_PRESETS.items():
            self.assertIsInstance(preset, CaptionPreset)
            self.assertEqual(preset.id, preset_id)
            self.assertTrue(preset.name)
            self.assertTrue(preset.tag)
            self.assertTrue(preset.sample_text)
            self.assertIsInstance(preset.settings, dict)
            self.assertIn("caption_font", preset.settings)
            self.assertIn("caption_highlight_color", preset.settings)

    def test_apply_and_detect_preset(self) -> None:
        for preset_id in VIRAL_PRESETS:
            opts = ProcessingOptions()
            apply_preset(opts, preset_id)
            self.assertEqual(detect_active_preset(opts), preset_id)

            # Alteração manual deve desmarcar o preset ativo (Custom)
            opts.caption_font_size += 3
            self.assertIsNone(detect_active_preset(opts))

    def test_apply_unknown_preset_keeps_options_intact(self) -> None:
        opts = ProcessingOptions()
        original_size = opts.caption_font_size
        apply_preset(opts, "preset_inexistente")
        self.assertEqual(opts.caption_font_size, original_size)

    def test_font_discovery_and_fallback(self) -> None:
        fonts = list_available_fonts()
        self.assertIsInstance(fonts, list)
        self.assertGreater(len(fonts), 0)
        self.assertIn("Arial", fonts)
        self.assertIn("Impact", fonts)

        path = find_font_path("Arial", bold=True)
        if path is not None:
            self.assertTrue(Path(path).exists())

    def test_ass_generation_for_all_presets(self) -> None:
        words = [
            CaptionWord(text="Segredo", start=0.5, end=0.9),
            CaptionWord(text="viral", start=0.9, end=1.4),
            CaptionWord(text="revelado", start=1.4, end=1.9),
            CaptionWord(text="agora", start=1.9, end=2.4),
        ]

        for preset_id, preset in VIRAL_PRESETS.items():
            opts = ProcessingOptions()
            apply_preset(opts, preset_id)

            ass_text = build_ass(words, opts, canvas_w=1080, canvas_h=1920)
            self.assertTrue(ass_text, f"Falha ao gerar ASS para {preset_id}")
            self.assertIn("[Script Info]", ass_text)
            self.assertIn("[V4+ Styles]", ass_text)
            self.assertIn("Style: Phrase,", ass_text)
            self.assertIn("Style: ActiveWord,", ass_text)

            opacity = float(preset.settings["caption_highlight_opacity"])
            if opacity > 0.01:
                self.assertIn("Dialogue: 0,", ass_text)
                self.assertIn(",Box,", ass_text)
            else:
                self.assertNotIn(",Box,", ass_text)
                self.assertIn("Dialogue: 2,", ass_text)
                self.assertIn(",ActiveWord,", ass_text)

        # Teste de escrita em disco via write_ass
        with tempfile.TemporaryDirectory() as tmp:
            ass_path = Path(tmp) / "test_preset.ass"
            opts = ProcessingOptions()
            apply_preset(opts, "hormozi_bold")
            written = write_ass(words, ass_path, opts, canvas_w=1080, canvas_h=1920)
            self.assertEqual(written, str(ass_path))
            self.assertTrue(ass_path.exists())
            content = ass_path.read_text(encoding="utf-8")
            self.assertIn("SEGREDO", content)

    def test_backward_compatibility_exports(self) -> None:
        word = CaptionWord(text="Teste", start=0.0, end=0.5)
        block = CaptionBlock(words=[word], start=0.0, end=0.5)
        self.assertEqual(len(block.words), 1)
        self.assertEqual(block.words[0].text, "Teste")

    def test_stronda_rise_animation_ass(self) -> None:
        words = [
            CaptionWord(text="CORTE", start=1.0, end=1.5),
            CaptionWord(text="VIRAL", start=1.5, end=2.2),
        ]
        opts = ProcessingOptions()
        apply_preset(opts, "stronda_rise")
        self.assertEqual(opts.caption_animation, "rise")
        self.assertEqual(opts.caption_outline_width, 8)
        self.assertEqual(detect_active_preset(opts), "stronda_rise")

        ass_text = build_ass(words, opts, canvas_w=1080, canvas_h=1920)
        self.assertIn("\\move(", ass_text)
        self.assertIn("\\fad(60,0)", ass_text)
        self.assertNotIn("\\frz", ass_text)
        self.assertNotIn("\\org(", ass_text)
        self.assertIn("ActiveWord", ass_text)
        self.assertIn("Phrase", ass_text)

        # Alias retrocompatível
        opts_alias = ProcessingOptions()
        apply_preset(opts_alias, "stronda_swing")
        self.assertEqual(detect_active_preset(opts_alias), "stronda_rise")

    def test_impact_glow_preset_and_ass(self) -> None:
        words = [
            CaptionWord(text="CORTE", start=1.0, end=1.5),
            CaptionWord(text="VIRAL", start=1.5, end=2.2),
        ]
        opts = ProcessingOptions()
        apply_preset(opts, "impact_glow")
        self.assertTrue(opts.caption_glow)
        self.assertEqual(opts.caption_outline_width, 1)
        self.assertEqual(opts.caption_outline_color, "#CBD5E1")
        self.assertEqual(opts.caption_animation, "rise")
        self.assertEqual(opts.caption_highlight_color, "#FFFFFF")
        self.assertEqual(detect_active_preset(opts), "impact_glow")

        ass_text = build_ass(words, opts, canvas_w=1080, canvas_h=1920)
        self.assertIn("Style: Glow,", ass_text)
        self.assertIn("Dialogue: 0,", ass_text)
        self.assertIn(",Glow,", ass_text)
        self.assertIn("\\blur6", ass_text)
        self.assertIn("\\1a&HFF&", ass_text)
        self.assertIn("\\move(", ass_text)
        # Outline do estilo Phrase é 1 com a cor cinza gelo (#CBD5E1 -> BGR &H00E1D5CB)
        self.assertIn("Style: Phrase,Impact,78,&H00FFFFFF,&H00FFFFFF,&H00E1D5CB,&H00E1D5CB,-1,0,0,0,100,100,0,0,1,1,1,7,0,0,0,1", ass_text)

    def test_stronda_red_box_preset_and_ass(self) -> None:
        words = [
            CaptionWord(text="SEM", start=1.0, end=1.4),
            CaptionWord(text="DESCULPA", start=1.4, end=2.0),
        ]
        opts = ProcessingOptions()
        apply_preset(opts, "stronda_red_box")
        self.assertEqual(opts.caption_max_words_per_line, 2)
        self.assertEqual(opts.caption_max_lines, 1)
        self.assertEqual(opts.caption_highlight_color, "#EF4444")
        self.assertAlmostEqual(opts.caption_highlight_opacity, 1.0)
        self.assertEqual(detect_active_preset(opts), "stronda_red_box")

        ass_text = build_ass(words, opts, canvas_w=1080, canvas_h=1920)
        self.assertIn("Dialogue: 0,", ass_text)
        self.assertIn(",Box,", ass_text)
        self.assertIn("\\fscx108\\fscy108", ass_text)

    def test_gui_widgets_and_settings_dialog_integration(self) -> None:
        grid = PresetGrid(VIRAL_PRESETS)
        self.assertEqual(len(grid.cards), 9)

        box = CollapsibleBox("Configurações Avançadas", expanded=False)
        self.assertFalse(box.is_expanded())
        box.set_expanded(True)
        self.assertTrue(box.is_expanded())

        opts = ProcessingOptions()
        apply_preset(opts, "tiktok_purple")
        dialog = SettingsDialog(opts)
        self.assertEqual(dialog.preset_grid.selected_preset(), "tiktok_purple")
        self.assertFalse(dialog.advanced_box.is_expanded())

        # Selecionar outro preset atualiza os controles e o preview
        dialog._on_preset_card_selected("hormozi_bold")
        self.assertEqual(dialog.preset_grid.selected_preset(), "hormozi_bold")
        self.assertEqual(dialog.caption_font_size.value(), 74)
        self.assertTrue(dialog.caption_uppercase.isChecked())
        self.assertAlmostEqual(dialog.caption_highlight_opacity.value(), 0.0)

        # Modificar um controle avançado muda para Custom (selected_preset = None)
        dialog.caption_font_size.setValue(68)
        self.assertIsNone(dialog.preset_grid.selected_preset())
        self.assertIn("Personalizado", dialog.preset_status_badge.text())

        # Renderização da prévia do celular sem erros para preset sem caixa e com caixa
        preview = PhonePreviewWidget(phone_width=196)
        preview.set_options(dialog._draft_options())
        preview.grab()


if __name__ == "__main__":
    unittest.main()
