import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import dynamic_zoom as dz
from core import framing, layouts, render
from core.options import ProcessingOptions


def _words(spans, text="palavra"):
    """Palavras de 0,3 s cobrindo cada trecho (inicio, fim)."""
    out = []
    for a, b in spans:
        t = a
        while t < b - 1e-6:
            out.append(SimpleNamespace(start=t, end=min(b, t + 0.3), text=text))
            t += 0.3
    return out


class _Track:
    """Trilha minima: caixas por frame (4 fps) com a cabeca se movendo."""

    def __init__(self, n, dx_per_frame=0.0):
        self.boxes = {
            i: (0.4 + dx_per_frame * i, 0.3, 0.12, 0.2) for i in range(n)
        }

    def median_box(self):
        return (0.4, 0.3, 0.12, 0.2)


def _shot(a, b):
    return SimpleNamespace(start=a, end=b, cx=0.46, cy=0.4, size=0.12)


FPS = framing.SAMPLE_FPS


class SpeechRunsTest(unittest.TestCase):
    def test_pausa_separa_falas(self):
        runs = dz.speech_runs(_words([(0, 3), (3.8, 5)]))
        self.assertEqual(len(runs), 2)
        self.assertAlmostEqual(runs[0][1], 3.0)

    def test_pausa_curta_nao_separa(self):
        self.assertEqual(len(dz.speech_runs(_words([(0, 2), (2.3, 4)]))), 1)

    def test_ponto_final_separa_com_pausa_menor(self):
        words = [SimpleNamespace(start=0, end=1, text="acabou."),
                 SimpleNamespace(start=1.3, end=2, text="Agora")]
        self.assertEqual(len(dz.speech_runs(words)), 2)


class BuildBeatsTest(unittest.TestCase):
    def _beats(self, spans, shots=None, cuts=(), end=20.0, track=None):
        shots = shots or [_shot(0, end)]
        track = track or _Track(int(end * FPS))
        return dz.build_beats(_words(spans), shots, [track] * len(shots),
                              list(cuts), end, FPS)

    def test_fala_longa_vira_zoom_ate_a_pausa_e_trava_1s(self):
        (beat,) = self._beats([(1, 5)])
        self.assertAlmostEqual(beat.start, 1.0)
        self.assertAlmostEqual(beat.peak, 5.0)
        self.assertAlmostEqual(beat.end, 6.0)
        self.assertGreater(beat.zoom, 1.0)
        self.assertLessEqual(beat.zoom, dz.ZOOM_MAX)

    def test_fala_curta_nao_gera_zoom(self):
        self.assertEqual(self._beats([(1, 2.5)]), [])

    def test_zoom_depende_da_duracao(self):
        (short,) = self._beats([(0, 2.5)])
        (long_,) = self._beats([(0, 6)])
        self.assertLess(short.zoom, long_.zoom)
        (huge,) = self._beats([(0, 15)])
        self.assertAlmostEqual(huge.zoom, dz.ZOOM_MAX)

    def test_trava_estende_ate_a_volta_da_fala_no_maximo_1_5s(self):
        (beat, _nxt) = self._beats([(0, 4), (5.3, 9)])
        self.assertAlmostEqual(beat.end, 5.3)
        beats = self._beats([(0, 4), (6.0, 9)])
        self.assertAlmostEqual(beats[0].end, 5.0)
        for b in beats:
            self.assertLessEqual(b.end - b.peak, dz.LOCK_MAX_S + 1e-6)

    def test_ciclos_nao_se_sobrepoem(self):
        beats = self._beats([(0, 4), (4.6, 9), (9.6, 14)])
        self.assertGreaterEqual(len(beats), 2)
        for a, b in zip(beats, beats[1:]):
            self.assertGreaterEqual(b.start, a.end)

    def test_troca_de_cena_encerra_o_ciclo(self):
        (beat,) = self._beats([(0, 8)], cuts=[5.0])
        self.assertLessEqual(beat.end, 5.0)
        self.assertLessEqual(beat.peak, 5.0)

    def test_nao_atravessa_troca_de_pessoa(self):
        shots = [_shot(0, 4), _shot(4, 12)]
        beats = self._beats([(0, 9)], shots=shots)
        for b in beats:
            self.assertTrue(b.end <= 4.0 or b.start >= 4.0)

    def test_plano_sem_rosto_nao_tem_zoom(self):
        beats = dz.build_beats(_words([(0, 6)]), [_shot(0, 10)], [None], [], 10, FPS)
        self.assertEqual(beats, [])

    def test_trava_segue_a_cabeca(self):
        (beat,) = self._beats([(0, 4)], track=_Track(80, dx_per_frame=0.01))
        self.assertAlmostEqual(beat.head[0][0], beat.start)
        self.assertGreater(beat.head[-1][1] - beat.head[0][1], 0.02)  # andou para a direita

    def test_serializa_no_plano(self):
        plan = framing.FramingPlan(src_width=1920, src_height=1080)
        plan.beats = self._beats([(0, 4)])
        back = framing.FramingPlan.from_dict(plan.to_dict())
        self.assertEqual(back.beats[0].to_list(), plan.beats[0].to_list())


class SafeZoomTest(unittest.TestCase):
    def test_rosto_medio_aceita_o_alvo(self):
        self.assertAlmostEqual(render.safe_zoom((0.5, 0.33, 0.42, 0.30), 1.3), 1.3)

    def test_rosto_alto_no_quadro_nao_trava_o_zoom(self):
        # caso real que antes ficava em ~1.06: rosto perto do topo
        self.assertGreater(render.safe_zoom((0.47, 0.31, 0.41, 0.29), 1.4), 1.3)

    def test_rosto_enorme_nao_ganha_zoom(self):
        self.assertAlmostEqual(render.safe_zoom((0.5, 0.45, 0.9, 0.6), 1.4), 1.0)

    def test_cabeca_ampliada_fica_dentro_com_margem(self):
        face = (0.47, 0.25, 0.41, 0.29)
        z = render.safe_zoom(face, 1.4)
        tx, ty = render.head_screen_target(face, z)
        cx, cy, fw, fh = face
        m = render.HEAD_MARGIN - 1e-9
        self.assertGreaterEqual(tx - fw * 0.6 * z, m)
        self.assertLessEqual(tx + fw * 0.6 * z, 1 - m)
        self.assertGreaterEqual(ty - fh * 0.85 * z, m)
        self.assertLessEqual(ty + fh * 0.65 * z, 1 - m)

    def test_alvo_maior_para_fala_longa(self):
        self.assertGreaterEqual(dz.zoom_for(dz.LONG_SPEECH_S), 1.1)
        self.assertAlmostEqual(dz.zoom_for(30), dz.ZOOM_MAX)


class DynamicFilterTest(unittest.TestCase):
    def _plan(self, face_x=0.4):
        track = _Track(80, dx_per_frame=0.002)
        track.boxes = {i: (face_x - 0.06 + 0.002 * i, 0.3, 0.12, 0.2) for i in range(80)}
        shots = [SimpleNamespace(start=0, end=20, cx=face_x, cy=0.4, size=0.12)]
        plan = framing.FramingPlan(src_width=1920, src_height=1080, shots=shots)
        plan.beats = dz.build_beats(_words([(1, 5), (6, 11)]), shots, [track], [], 20, FPS)
        return plan

    def _filter(self, layout_id, plan, work_dir=None):
        lay = layouts.get_layout(layout_id)
        return render.build_layout_filter(
            lay, layouts.slot_heights(lay, 1920), width=1080,
            options=ProcessingOptions(), plan=plan, src_size=(1920, 1080),
            work_dir=work_dir,
        )

    def test_formato_dinamico_registrado(self):
        lay = layouts.get_layout("follow_dynamic")
        self.assertTrue(lay.dynamic)
        self.assertTrue(lay.needs_vision)
        self.assertFalse(layouts.get_layout("follow").dynamic)

    def test_filtro_usa_recorte_variavel(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self._filter("follow_dynamic", self._plan(), tmp)
            self.assertIn("sendcmd=f=zoom_s0.cmd", f)
            self.assertTrue((Path(tmp) / "zoom_s0.cmd").is_file())
        self.assertTrue(f.endswith("[v]"))
        self.assertNotIn("sendcmd", self._filter("follow", self._plan()))

    def test_sem_ciclos_cai_no_seguir_normal(self):
        plan = self._plan()
        plan.beats = []
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotIn("sendcmd", self._filter("follow_dynamic", plan, tmp))

    def _screen_pos(self, plan, t):
        """Posicao de tela (0-1) do rosto no instante t."""
        cw, ch, rects = render.dynamic_crop_rects(plan, 1080, 1920, 1920, 1080)
        _t, x, y, rw, rh = min(rects, key=lambda r: abs(r[0] - t))
        beat = next(b for b in plan.beats if b.start <= t < b.end)
        dx, dy = render._head_delta(beat.head, t)
        fx = (beat.face[0] + dx) * 1920
        return (fx - x) / rw, rw / cw

    def test_zoom_centraliza_o_rosto_na_horizontal(self):
        for face_x in (0.3, 0.5, 0.7):
            plan = self._plan(face_x)
            beat = plan.beats[0]
            pos, scale = self._screen_pos(plan, beat.peak - 0.01)
            self.assertLess(scale, 0.95, "precisa ter zoom de verdade")
            self.assertAlmostEqual(pos, render.FACE_SCREEN_X, delta=0.03, msg=face_x)

    def test_trava_mantem_o_rosto_no_lugar_com_a_cabeca_andando(self):
        plan = self._plan()
        beat = plan.beats[0]
        a, _ = self._screen_pos(plan, beat.peak + 0.05)
        b, _ = self._screen_pos(plan, beat.end - 0.05)
        self.assertAlmostEqual(a, b, delta=0.02)

    def test_zoom_comeca_sem_salto(self):
        plan = self._plan()
        cw, ch, rects = render.dynamic_crop_rects(plan, 1080, 1920, 1920, 1080)
        beat = plan.beats[0]
        before = min(rects, key=lambda r: abs(r[0] - (beat.start - 0.05)))
        after = min(rects, key=lambda r: abs(r[0] - (beat.start + 0.05)))
        self.assertLessEqual(abs(before[1] - after[1]), 12)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg ausente")
    def test_ffmpeg_aceita_o_filtro(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self._filter("follow_dynamic", self._plan(), tmp)
            out = Path(tmp) / "o.mp4"
            proc = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                 "-i", "testsrc2=s=1920x1080:r=30:d=8", "-filter_complex", f,
                 "-map", "[v]", "-frames:v", "240", "-y", str(out)],
                capture_output=True, text=True, cwd=tmp,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", str(out)], capture_output=True, text=True,
            )
            self.assertEqual(probe.stdout.strip(), "1080,1920")


if __name__ == "__main__":
    unittest.main()
