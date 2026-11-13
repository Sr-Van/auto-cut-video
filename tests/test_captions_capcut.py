import unittest

from core.captions import CaptionWord
from core.captions.ass_writer import ass_time, build_ass
from core.captions.layout import keyword_index
from core.captions.presets import VIRAL_PRESETS, apply_preset, detect_active_preset
from core.options import ProcessingOptions

CAPCUT_IDS = (
    "capcut_revelado",
    "capcut_glow_word",
    "capcut_keyword",
    "capcut_keyword_neon",
)


def _words():
    texts = ["me", "chama", "aqui", "no", "WhatsApp"]
    return [
        CaptionWord(start=i * 0.3, end=i * 0.3 + 0.25, text=t)
        for i, t in enumerate(texts)
    ]


def _opts(preset_id):
    return apply_preset(ProcessingOptions(captions_enabled=True), preset_id)


def _events(ass, style):
    return [
        line for line in ass.splitlines()
        if line.startswith("Dialogue:") and f",{style},," in line
    ]


class CapcutPresetTests(unittest.TestCase):
    def test_presets_registered_and_detected(self):
        for preset_id in CAPCUT_IDS:
            self.assertIn(preset_id, VIRAL_PRESETS)
            self.assertEqual(detect_active_preset(_opts(preset_id)), preset_id)

    def test_switching_preset_resets_new_fields(self):
        opts = _opts("capcut_revelado")
        apply_preset(opts, "hormozi_bold")
        self.assertEqual(opts.caption_karaoke_mode, "active")
        self.assertFalse(opts.caption_italic)
        self.assertEqual(detect_active_preset(opts), "hormozi_bold")

    def test_revelado_hidden_words_drop_in_with_focus(self):
        words = _words()
        ass = build_ass(words, _opts("capcut_revelado"), 1080, 1920)
        style = next(l for l in ass.splitlines() if l.startswith("Style: Phrase"))
        self.assertEqual(style.split(",")[1], "Poppins")
        self.assertEqual(style.split(",")[8], "-1")  # Italic
        # palavras nao ditas ficam escondidas: nada de "Upcoming"
        self.assertFalse(_events(ass, "Upcoming"))
        lit = _events(ass, "Phrase")
        # cada palavra entra quando e falada, caindo de cima e ganhando opacidade
        import re

        for line, word in zip(lit, words):
            self.assertEqual(line.split(",")[1], ass_time(word.start))
            x0, y0, x1, y1 = map(float, re.search(r"move\(([\d.]+),([\d.]+),([\d.]+),([\d.]+)", line).groups())
            self.assertEqual(x0, x1)
            self.assertLess(y0, y1)
            self.assertIn("\\alpha&HFF&\\t(0,", line)
        self.assertEqual(len({l.split(",")[2] for l in lit}), 1)  # ficam ate o fim
        # amarelo = palavra em foco (sem aumentar), glow escuro de fundo
        focus = [l for l in lit if "\\1c&H15CCFA&" in l]
        self.assertEqual([l.rsplit("}", 1)[1] for l in focus], ["WhatsApp"])
        self.assertNotIn("\\fs", focus[0])
        self.assertTrue(all("\\3c&H000000&" in l for l in _events(ass, "Glow")))

    def test_glow_word_uses_blur_in_one_word_per_block(self):
        ass = build_ass(_words(), _opts("capcut_glow_word"), 1080, 1920)
        phrase = _events(ass, "Phrase")
        self.assertEqual(len(phrase), 5)
        self.assertTrue(all("\\blur12\\fscx135" in l for l in phrase))
        self.assertTrue(all("\\blur14" in l for l in _events(ass, "Glow")))

    def test_keyword_stairs_rise_and_emphasis(self):
        opts = _opts("capcut_keyword")
        ass = build_ass(_words(), opts, 1080, 1920)
        active = _events(ass, "ActiveWord")
        # cada palavra sobe ganhando opacidade
        self.assertTrue(
            all("\\move(" in l and "\\alpha&HFF&\\t(0," in l for l in active)
        )
        # so a ultima palavra de conteudo de cada cena ganha cor
        emphasized = [l for l in active if "\\1c" in l]
        self.assertEqual(
            [l.rsplit("}", 1)[1] for l in emphasized], ["chama", "WhatsApp"]
        )
        big_fs = f"\\fs{round(opts.caption_font_size * opts.caption_emphasis_scale)}"
        sized = {l.rsplit("}", 1)[1] for l in active if big_fs in l}
        self.assertEqual(sized, {"chama", "WhatsApp"})  # apoio fica pequeno
        # sombra translucida alem do contorno
        style = next(l for l in ass.splitlines() if l.startswith("Style: Phrase"))
        self.assertEqual(style.split(",")[16:18], ["2", "5"])

    def test_stairs_rows_match_reference_prints(self):
        from core.captions.layout import mark_emphasis, stairs_rows
        from core.captions.models import CaptionBlock

        opts = _opts("capcut_keyword")
        for text, expected in (
            ("de recusar um convite", [["de", "recusar"], ["um", "convite"]]),
            ("Paris pro fashion week?", [["Paris", "pro"], ["fashion"], ["week?"]]),
        ):
            words = [CaptionWord(i, i + 0.5, t) for i, t in enumerate(text.split())]
            mark_emphasis([CaptionBlock(0, 4, words)], opts)
            rows = [[w.text for w in row] for row in stairs_rows(words)]
            self.assertEqual(rows, expected)
            self.assertTrue(words[-1].emphasis)

    def test_stairs_rows_step_right_and_down(self):
        import re

        words = [
            CaptionWord(i * 0.35, i * 0.35 + 0.3, t)
            for i, t in enumerate("Paris pro fashion week?".split())
        ]
        ass = build_ass(words, _opts("capcut_keyword"), 1080, 1920)
        pos = {
            l.rsplit("}", 1)[1]: tuple(map(float, re.search(r"move\(([\d.]+),[\d.]+,[\d.]+,([\d.]+)", l).groups()))
            for l in _events(ass, "ActiveWord")
        }
        self.assertLess(pos["Paris"][0], pos["fashion"][0])
        self.assertLess(pos["fashion"][0], pos["week?"][0])
        self.assertLess(pos["Paris"][1], pos["fashion"][1])
        self.assertLess(pos["fashion"][1], pos["week?"][1])
        # "pro" fica ao lado de Paris, alinhada pelo topo (acima da base dela)
        self.assertGreater(pos["pro"][0], pos["Paris"][0])

    def test_keyword_index_prefers_numbers(self):
        words = [CaptionWord(0, 1, t) for t in ["30", "efeitos", "pra", "deixar"]]
        self.assertEqual(keyword_index(words), 0)
        words = [CaptionWord(0, 1, t) for t in ["de", "um", "pra"]]
        self.assertIsNone(keyword_index(words))

    def test_legacy_preset_output_unchanged_shape(self):
        ass = build_ass(_words(), _opts("hormozi_bold"), 1080, 1920)
        self.assertNotIn("\\1c", ass.split("[Events]")[1])
        self.assertFalse(_events(ass, "Upcoming"))


class BundledFontTests(unittest.TestCase):
    def test_bundled_fonts_resolve_bold_and_italic(self):
        import os

        from core.captions.fonts import find_font_path, libass_scale

        for family in ("Poppins", "Montserrat"):
            bold = find_font_path(family, True)
            italic = find_font_path(family, True, True)
            self.assertTrue(bold.endswith(f"{family}-Bold.ttf"), bold)
            self.assertTrue(italic.endswith(f"{family}-BoldItalic.ttf"), italic)
            self.assertTrue(os.path.exists(bold))
            # libass dimensiona pelas metricas win: bem menor que o Arial
            self.assertLess(libass_scale(bold), 0.7)


if __name__ == "__main__":
    unittest.main()


class CaptionPreviewTests(unittest.TestCase):
    def test_preview_draws_every_preset_with_core_layout(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtWidgets import QApplication

        from core.layouts import caption_options
        from gui.caption_preview import draw_caption
        from gui.widgets import SAMPLE_WORDS

        QApplication.instance() or QApplication([])
        for preset_id in VIRAL_PRESETS:
            opts = caption_options(_opts(preset_id))
            img = QImage(180, 320, QImage.Format_ARGB32)
            img.fill(QColor("#000000"))
            painter = QPainter(img)
            draw_caption(painter, QRectF(0, 0, 180, 320), opts, SAMPLE_WORDS)
            painter.end()
            lit = sum(
                1
                for y in range(0, 320, 2)
                for x in range(0, 180, 2)
                if QColor(img.pixel(x, y)).lightness() > 120
            )
            self.assertGreater(lit, 0, preset_id)
