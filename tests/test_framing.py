import unittest
from types import SimpleNamespace

from core import framing


@unittest.skipUnless(framing.available(), "OpenCV/numpy ausentes")
class FramingDecisionTest(unittest.TestCase):
    def _track(self, box, frames, motion=None):
        t = framing.Track()
        for i in frames:
            t.boxes[i] = box
        t.motion = dict(motion or {})
        return t

    def test_quem_mexe_a_boca_falando_ganha_o_foco(self):
        n = 40
        a = self._track((0.15, 0.3, 0.2, 0.3), range(n), {i: 1.0 for i in range(n)})
        b = self._track((0.65, 0.3, 0.2, 0.3), range(n),
                        {i: (8.0 if i >= 20 else 0.5) for i in range(n)})
        words = [SimpleNamespace(start=0.0, end=n / framing.SAMPLE_FPS)]
        plan = framing.plan_from_tracks([a, b], n, words, 1920, 1080, want_cam=False)
        self.assertEqual(len(plan.shots), 2)
        self.assertLess(plan.shots[0].cx, 0.5)
        self.assertGreater(plan.shots[1].cx, 0.5)

    def test_planos_curtos_sao_absorvidos(self):
        choice = [0] * 20 + [1] * 2 + [0] * 20
        shots = framing.smooth_shots(choice, min_frames=6)
        self.assertEqual(shots, [(0, 42, 0)])

    def test_cena_sem_rosto_usa_centro_sem_mudar_formato(self):
        n = 60  # 15 s; cena sem rosto de 5 s a 9 s
        gap = set(range(20, 36))
        frames = [i for i in range(n) if i not in gap]
        a = self._track((0.15, 0.25, 0.2, 0.3), frames, {i: 2.0 for i in frames})
        plan = framing.plan_from_tracks([a], n, None, 1920, 1080, want_cam=False,
                                        cuts=[20, 36])
        self.assertEqual(len(plan.shots), 3)
        mid = plan.shots[1]
        self.assertAlmostEqual(mid.start, 5.0)
        self.assertAlmostEqual(mid.end, 9.0)
        self.assertAlmostEqual(mid.cx, 0.5)
        self.assertEqual(plan.scene_cuts, [5.0, 9.0])

    def test_rosto_some_sem_troca_de_cena_mantem_posicao(self):
        n = 60
        frames = [i for i in range(n) if not 20 <= i < 36]
        a = self._track((0.15, 0.25, 0.2, 0.3), frames)
        plan = framing.plan_from_tracks([a], n, None, 1920, 1080, want_cam=False)
        self.assertEqual(len(plan.shots), 1)
        self.assertLess(plan.shots[0].cx, 0.4)

    def test_inicio_sem_deteccao_usa_primeiro_rosto(self):
        n = 40
        a = self._track((0.6, 0.25, 0.2, 0.3), range(10, n))
        plan = framing.plan_from_tracks([a], n, None, 1920, 1080, want_cam=False)
        self.assertEqual(plan.shots[0].start, 0.0)
        self.assertGreater(plan.shots[0].cx, 0.6)

    def _moldura_frames(self, banner: bool, n=48, cut=24):
        import numpy as np

        rng = np.random.default_rng(1)
        cam_a = rng.integers(0, 255, (180, 320), dtype=np.uint8)
        cam_b = rng.integers(0, 255, (180, 320), dtype=np.uint8)
        frames = []
        for i in range(n):
            f = (cam_a if i < cut else cam_b).copy()  # cameras travadas
            if banner:
                f[144:, :] = 90  # faixa de baixo
                f[:, 256:] = 90  # faixa da direita
            frames.append(f)
        return frames

    def test_moldura_que_atravessa_troca_de_camera(self):
        spans = framing.live_boxes(self._moldura_frames(True), cuts=[24])
        self.assertEqual(len(spans), 1)
        a, b, box = spans[0]
        self.assertEqual((a, b), (0, 48))
        self.assertAlmostEqual(box[2], 0.8, delta=0.04)
        self.assertAlmostEqual(box[3], 0.8, delta=0.04)

    def test_parede_parada_de_estudio_nao_e_moldura(self):
        # camera travada: tudo parado, mas muda inteiro quando a camera troca
        self.assertEqual(framing.live_boxes(self._moldura_frames(False), cuts=[24]), [])

    def test_sem_troca_de_cena_nao_arrisca(self):
        frames = self._moldura_frames(True, cut=999)
        self.assertEqual(framing.live_boxes(frames, cuts=[]), [])

    def test_rosto_mapeado_para_tela_restaurada(self):
        live = (0.0, 0.0, 0.8, 0.8)
        box = framing.map_to_restored((0.4, 0.4, 0.08, 0.08), live, 1920, 1080)
        self.assertAlmostEqual(box[0], 0.5, delta=0.01)
        self.assertAlmostEqual(box[2], 0.1, delta=0.01)

    def test_tomada_aberta_curta_foca_em_quem_fala(self):
        # 0-5 s close no convidado; 5-6 s tomada aberta da mesa (1 s):
        # apresentador falando a esquerda e um poster parado a direita.
        n = 40
        guest = self._track((0.4, 0.2, 0.25, 0.35), [i for i in range(n) if not 20 <= i < 24],
                            {i: 1.0 for i in range(n)})
        host = self._track((0.15, 0.3, 0.1, 0.15), range(20, 24), {i: 6.0 for i in range(20, 24)})
        poster = self._track((0.7, 0.2, 0.12, 0.18), range(20, 24), {i: 0.0 for i in range(20, 24)})
        tracks = [guest, host, poster]
        plan = framing.plan_from_tracks(tracks, n, None, 1920, 1080, want_cam=False,
                                        cuts=[20, 24])
        mesa = [s for s in plan.shots if s.start >= 4.9 and s.end <= 6.1]
        self.assertEqual(len(mesa), 1)
        self.assertLess(mesa[0].cx, 0.3)

    def test_rosto_de_cena_curta_vira_trilha(self):
        box = (0.2, 0.3, 0.1, 0.15)
        faces = [[] for _ in range(40)]
        for i in range(20, 24):
            faces[i] = [box]
        self.assertEqual(len(framing.build_tracks(faces, cuts=[20, 24])), 1)

    def test_trilha_nao_atravessa_troca_de_cena(self):
        box = (0.4, 0.25, 0.2, 0.3)
        faces = [[box]] * 20
        tracks = framing.build_tracks(faces, cuts=[10])
        self.assertEqual(len(tracks), 2)

    def test_troca_de_cena_detectada(self):
        import numpy as np

        dark = np.zeros((90, 160), dtype=np.uint8)
        bright = np.full((90, 160), 200, dtype=np.uint8)
        self.assertEqual(framing.scene_cuts([dark, dark, bright, bright]), [2])

    def test_webcam_pequena_no_canto(self):
        cam = self._track((0.82, 0.75, 0.08, 0.12), range(30))
        box = framing.find_cam([cam])
        self.assertIsNotNone(box)
        self.assertGreater(box[0], 0.5)
        content = framing.content_without_cam(box)
        self.assertGreaterEqual(content[2], 0.65)

    def test_rosto_grande_nao_e_webcam(self):
        face = self._track((0.35, 0.2, 0.3, 0.45), range(30))
        self.assertIsNone(framing.find_cam([face]))


class FramingFallbackTest(unittest.TestCase):
    def test_plano_serializa(self):
        plan = framing.FramingPlan(src_width=1920, src_height=1080,
                                   shots=[framing.FocusShot(0, 1, 0.5, 0.5, 0.1)],
                                   cam_box=(0.8, 0.7, 0.1, 0.2))
        again = framing.FramingPlan.from_dict(plan.to_dict())
        self.assertEqual(again.shots[0].cx, 0.5)
        self.assertEqual(again.cam_box, (0.8, 0.7, 0.1, 0.2))

    def test_sem_opencv_devolve_plano_vazio(self):
        original = framing.cv2
        framing.cv2 = None
        try:
            plan = framing.analyze_clip("C:/nao/existe.mp4", 0, 5)
            self.assertEqual(plan.shots, [])
        finally:
            framing.cv2 = original


if __name__ == "__main__":
    unittest.main()
