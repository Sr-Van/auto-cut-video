import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from core.captions import (
    PRESETS,
    RECOMMENDED_FONTS,
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
from gui.widgets import (
    CollapsibleBox,
    FontComboBox,
    FontPreviewDelegate,
    PhonePreviewWidget,
    PresetGrid,
)


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
            "capcut_revelado",
            "capcut_glow_word",
            "capcut_keyword",
            "capcut_keyword_neon",
        }
        self.assertEqual(set(VIRAL_PRESETS.keys()), expected_ids)
        self.assertEqual(len(PRESETS), 13)

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
            elif (
                preset.settings["caption_highlight_color"].upper()
                != preset.settings["caption_text_color"].upper()
            ):
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
        self.assertEqual(len(grid.cards), 13)

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

    def test_font_combo_preview_delegate_and_hover(self) -> None:
        opts = ProcessingOptions(caption_font="Arial", captions_enabled=True)
        dialog = SettingsDialog(opts, embedded=True)
        self.assertIsInstance(dialog.caption_font, FontComboBox)
        self.assertIsInstance(dialog.layout_text_font, FontComboBox)
        self.assertIsInstance(
            dialog.caption_font.itemDelegate(), FontPreviewDelegate
        )

        combo = dialog.caption_font
        delegate = combo.itemDelegate()
        model = combo.model()

        # Cabeçalho "Recomendadas" no topo + seção de outras fontes abaixo
        hdr_idx = model.index(0, 0)
        self.assertEqual(
            hdr_idx.data(Qt.AccessibleDescriptionRole), "section_header"
        )
        self.assertEqual(hdr_idx.data(Qt.DisplayRole), "Recomendadas")
        self.assertEqual(hdr_idx.flags(), Qt.NoItemFlags)
        self.assertEqual(
            delegate.sizeHint(QStyleOptionViewItem(), hdr_idx).height(),
            FontPreviewDelegate.HEADER_HEIGHT,
        )

        other_hdr_row = next(
            (
                r
                for r in range(1, combo.count())
                if model.index(r, 0).data(Qt.AccessibleDescriptionRole)
                == "section_header"
            ),
            None,
        )
        self.assertIsNotNone(other_hdr_row)
        self.assertEqual(
            model.index(other_hdr_row, 0).data(Qt.DisplayRole),
            "Outras fontes do sistema",
        )

        # Fontes recomendadas ficam no bloco superior e sem duplicatas no combo
        rec_items = [combo.itemData(r) for r in range(1, other_hdr_row)]
        other_items = [
            combo.itemData(r)
            for r in range(other_hdr_row + 1, combo.count())
            if combo.itemData(r)
        ]
        self.assertGreater(len(rec_items), 0)
        for name in rec_items:
            self.assertIn(name, RECOMMENDED_FONTS)
        for excluded in ("Arial", "Segoe UI", "Verdana"):
            self.assertNotIn(excluded, rec_items)
            self.assertNotIn(excluded, RECOMMENDED_FONTS)
        for bundled in (
            "Inter",
            "Montserrat",
            "Poppins",
            "Lato",
            "Fira Sans",
            "Bebas Neue",
            "EB Garamond",
            "Bodoni Moda",
        ):
            self.assertIn(bundled, rec_items)
            resolved = find_font_path(bundled)
            self.assertIsNotNone(resolved)
            self.assertTrue(Path(resolved).exists())
        self.assertIn("Arial", other_items)
        all_fonts = [
            combo.itemData(r)
            for r in range(combo.count())
            if combo.itemData(r)
        ]
        self.assertEqual(len(all_fonts), len({f.lower() for f in all_fonts}))

        # SizeHint para linha de fonte
        font_idx = model.index(1, 0)
        self.assertEqual(
            delegate.sizeHint(QStyleOptionViewItem(), font_idx).height(),
            FontPreviewDelegate.ROW_HEIGHT,
        )

        # Pintura do delegate (cabeçalho, normal, selecionado e hover) sem erros
        pixmap = QPixmap(340, 60)
        painter = QPainter(pixmap)
        try:
            opt = QStyleOptionViewItem()
            opt.rect = QRect(0, 0, 320, FontPreviewDelegate.HEADER_HEIGHT)
            delegate.paint(painter, opt, hdr_idx)
            delegate.paint(painter, opt, model.index(other_hdr_row, 0))
            opt.rect = QRect(0, 0, 320, FontPreviewDelegate.ROW_HEIGHT)
            delegate.paint(painter, opt, font_idx)
            opt.state |= QStyle.State_Selected
            delegate.paint(painter, opt, font_idx)
            opt.state = QStyle.State_MouseOver
            delegate.paint(painter, opt, font_idx)
        finally:
            painter.end()

        # ensure_font não insere acima do cabeçalho "Recomendadas"
        custom_idx = combo.ensure_font("MinhaFonteCustom")
        self.assertGreater(custom_idx, 0)
        self.assertEqual(model.index(0, 0).data(Qt.DisplayRole), "Recomendadas")

        # Sincronização de maiúsculas/itálico na amostra do seletor
        dialog.caption_uppercase.setChecked(True)
        dialog.caption_italic.setChecked(True)
        self.assertEqual(delegate._effective_sample(), "LEGENDA · ABC 123")
        self.assertTrue(delegate._italic)

        # Prévia transitória ao navegar na lista sem alterar options persistidas
        impact_idx = combo.findText("Impact", Qt.MatchFixedString)
        if impact_idx >= 0 and impact_idx != combo.currentIndex():
            dialog.show()
            combo.showPopup()
            QApplication.processEvents()
            self.assertGreaterEqual(combo.view().width(), 320)
            combo.highlighted.emit(impact_idx)
            self.assertEqual(dialog.preview_widget._options.caption_font, "Impact")
            self.assertEqual(dialog.options.caption_font, "Arial")
            combo.hidePopup()
            QApplication.processEvents()
            self.assertEqual(dialog.preview_widget._options.caption_font, "Arial")
            dialog.close()


if __name__ == "__main__":
    unittest.main()
