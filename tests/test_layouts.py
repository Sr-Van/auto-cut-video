import unittest
from types import SimpleNamespace

from core import layouts, render
from core.options import ProcessingOptions


class LayoutCatalogTest(unittest.TestCase):
    def test_alturas_pares_somam_a_tela(self):
        for layout in layouts.LAYOUTS.values():
            self.assertAlmostEqual(sum(s.height for s in layout.slots), 1.0, places=6)
            heights = layouts.slot_heights(layout, 1920)
            self.assertEqual(sum(heights), 1920, layout.id)
            self.assertTrue(all(h % 2 == 0 for h in heights), layout.id)

    def test_id_desconhecido_cai_no_centralizado(self):
        self.assertEqual(layouts.get_layout("nao-existe").id, "center")
        self.assertEqual(ProcessingOptions(layout_id="xyz").layout_id, "center")

    def test_requisitos_de_imagem(self):
        lay = layouts.get_layout("image_video")
        self.assertTrue(layouts.missing_requirements(lay, ""))
        self.assertFalse(layouts.missing_requirements(layouts.get_layout("title_middle"), ""))

    def test_fonte_do_texto_da_faixa(self):
        clip = {"title": "Titulo", "hook_text": "Gancho"}
        self.assertEqual(layouts.clip_band_text(clip, "hook"), "Gancho")
        self.assertEqual(layouts.clip_band_text(clip, "title"), "Titulo")
        self.assertEqual(layouts.clip_band_text(clip, "custom", "Fixo"), "Fixo")
        self.assertEqual(layouts.clip_band_text({"title": "T"}, "hook"), "T")


class LayoutFilterTest(unittest.TestCase):
    def _filter(self, layout_id, plan=None, lines=("linha",)):
        lay = layouts.get_layout(layout_id)
        heights = layouts.slot_heights(lay, 1920)
        return render.build_layout_filter(
            lay, heights, width=1080, options=ProcessingOptions(), plan=plan,
            src_size=(1920, 1080), band_lines=list(lines), band_font_size=48,
            font_file="band_font.ttf", image_input=1,
        )

    def test_todos_os_formatos_terminam_em_v(self):
        for lid, lay in layouts.LAYOUTS.items():
            if lay.legacy:
                continue
            f = self._filter(lid)
            self.assertTrue(f.endswith("[v]"), lid)
            if len(lay.slots) > 1:
                self.assertIn(f"vstack=inputs={len(lay.slots)}:shortest=1", f)

    def test_texto_vai_por_arquivo_e_nao_inline(self):
        f = self._filter("title_middle", lines=("O que: aconteceu, 100%",))
        self.assertIn("textfile='band_1_0.txt'", f)
        self.assertNotIn("aconteceu", f)

    def test_focus_segue_planos(self):
        plan = SimpleNamespace(
            shots=[
                SimpleNamespace(start=0, end=3, cx=0.3, cy=0.4, size=0.1),
                SimpleNamespace(start=3, end=8, cx=0.7, cy=0.4, size=0.1),
            ],
            cam_box=None, content_box=None,
        )
        f = self._filter("follow", plan=plan)
        self.assertIn("if(lt(t,3.00)", f)

    def test_quebra_de_texto_cabe_na_faixa(self):
        lines, size = render.wrap_band_text("palavra " * 30, 1080, 268)
        self.assertLessEqual(len(lines), 3)
        self.assertGreaterEqual(size, 18)
        self.assertEqual(render.wrap_band_text("", 1080, 268), ([], 0))

    def test_musica_com_e_sem_voz(self):
        self.assertIn("sidechaincompress", render.build_music_filter(1, 0.2, True))
        self.assertNotIn("sidechaincompress", render.build_music_filter(1, 0.2, False))


if __name__ == "__main__":
    unittest.main()


class CaptionPlacementTest(unittest.TestCase):
    def _place(self, layout_id, size=72):
        opts = ProcessingOptions(layout_id=layout_id, caption_font_size=size)
        adj = layouts.caption_options(opts)
        lay = layouts.get_layout(layout_id)
        heights = layouts.slot_heights(lay, opts.height)
        bottom = opts.height - adj.caption_margin_bottom
        top_of_slot = sum(heights[: lay.caption_slot])
        return adj, bottom, top_of_slot, top_of_slot + heights[lay.caption_slot]

    def test_legenda_fica_dentro_do_slot_certo(self):
        for lid in layouts.LAYOUTS:
            adj, bottom, top, end = self._place(lid)
            self.assertGreater(bottom, top, lid)
            self.assertLessEqual(bottom, end, lid)

    def test_tamanhos_por_formato(self):
        sizes = {lid: self._place(lid)[0].caption_font_size for lid in layouts.LAYOUTS}
        self.assertGreater(sizes["center"], 72)
        self.assertLess(sizes["react"], sizes["title_middle"])
        self.assertLess(sizes["title_middle"], sizes["center"])

    def test_nao_altera_as_opcoes_originais(self):
        opts = ProcessingOptions(layout_id="react", caption_font_size=72)
        layouts.caption_options(opts)
        self.assertEqual(opts.caption_font_size, 72)


class BandSafetyTest(unittest.TestCase):
    def test_texto_da_faixa_nao_e_interpretado_pelo_drawtext(self):
        layout = layouts.get_layout("title_middle")
        f = render.build_layout_filter(
            layout, layouts.slot_heights(layout, 1920), width=1080,
            options=ProcessingOptions(), band_lines=["MER%@"],
            band_font_size=60, font_file="band_font.ttf",
        )
        self.assertIn("expansion=none", f)


class ModelIntegrityTest(unittest.TestCase):
    def test_modelo_yunet_confere_com_o_hash(self):
        from core import framing

        if framing.MODEL_PATH.is_file():
            self.assertTrue(framing._model_ok())
