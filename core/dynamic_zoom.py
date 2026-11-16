"""Edicao dinamica do "seguir quem fala": ciclos de zoom + trava na cabeca.

Para cada fala longa (palavras do Whisper sem pausa) dentro de um mesmo plano
(mesma pessoa, sem troca de cena):

1. zoom: do inicio da fala ate a pausa, a camera aproxima e leva o rosto
   para o centro. Quanto mais longa a fala, maior o zoom (com teto); o
   render ainda limita o zoom para a cabeca nunca sair do quadro.
2. trava: com o zoom mantido, o quadro acompanha o movimento da cabeca por
   LOCK_S (1 s). Se a pessoa volta a falar em ate LOCK_MAX_S (1,5 s), a
   trava se estende ate esse instante, para a volta cair junto com a fala.
3. volta: a camera retorna seca ao enquadramento normal do "seguir quem
   fala" e o ciclo recomeca na proxima fala longa.

Aqui so ficam as decisoes de tempo (puras, testaveis). A geometria (quanto
de zoom cabe e o recorte de cada quadro) fica em `core.render`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PAUSE_S = 0.5  # silencio entre palavras que encerra uma fala
PUNCT_PAUSE_S = 0.25  # pausa menor basta depois de ponto final/interrogacao
LONG_SPEECH_S = 2.0  # fala minima para virar um ciclo de zoom
LOCK_S = 1.0  # trava na cabeca
LOCK_MAX_S = 1.5
MIN_LOCK_S = 0.35  # trava menor que isso (troca de cena logo apos) e descartada
ZOOM_BASE = 1.12  # zoom de uma fala longa minima
ZOOM_PER_S = 0.06  # +6% por segundo alem do minimo
ZOOM_MAX = 1.40  # teto (o render ainda limita pelo tamanho da cabeca)
MIN_ZOOM = 1.06  # abaixo disso o ciclo nao vale a pena
SHOT_SETTLE_S = 0.45  # espera o deslize de troca de pessoa terminar

_END_PUNCT = (".", "!", "?", "…")


@dataclass
class ZoomBeat:
    start: float  # inicio da fala (comeca o zoom)
    peak: float  # pausa (zoom maximo, comeca a trava)
    end: float  # fim da trava (volta ao enquadramento normal)
    zoom: float  # zoom alvo pela duracao da fala (o render pode reduzir)
    face: tuple[float, float, float, float]  # cx, cy, w, h normalizados
    # Trilha suavizada da cabeca no ciclo todo (zoom + trava), relativa ao
    # centro em `face`: [(t, dx, dy)] normalizados pela largura/altura da origem.
    head: list[tuple[float, float, float]] = field(default_factory=list)

    def to_list(self) -> list:
        return [self.start, self.peak, self.end, self.zoom, list(self.face),
                [list(p) for p in self.head]]

    @classmethod
    def from_list(cls, data) -> "ZoomBeat":
        start, peak, end, zoom, face, head = data
        return cls(float(start), float(peak), float(end), float(zoom),
                   tuple(float(v) for v in face),
                   [tuple(float(v) for v in p) for p in head])


def speech_runs(words) -> list[tuple[float, float]]:
    """Agrupa palavras em falas continuas separadas por pausas."""
    runs: list[tuple[float, float]] = []
    prev_text = ""
    for w in sorted(words or [], key=lambda w: float(w.start)):
        a, b = float(w.start), float(w.end)
        if runs:
            gap = a - runs[-1][1]
            limit = PUNCT_PAUSE_S if prev_text.endswith(_END_PUNCT) else PAUSE_S
            if gap < limit:
                runs[-1] = (runs[-1][0], max(runs[-1][1], b))
                prev_text = str(getattr(w, "text", "") or "").strip()
                continue
        runs.append((a, b))
        prev_text = str(getattr(w, "text", "") or "").strip()
    return runs


def zoom_for(duration: float) -> float:
    extra = max(0.0, duration - LONG_SPEECH_S)
    return min(ZOOM_MAX, ZOOM_BASE + ZOOM_PER_S * extra)


def build_beats(words, shots, shot_tracks, cuts, clip_end: float,
                sample_fps: float) -> list[ZoomBeat]:
    """Ciclos de zoom/trava para as falas longas do corte.

    `shots` sao os FocusShot do plano e `shot_tracks[i]` a trilha (Track) do
    rosto do plano i, ou None quando o plano e centro/posicao mantida.
    """
    runs = speech_runs(words)
    starts = [a for a, _b in runs]
    beats: list[ZoomBeat] = []
    free_from = 0.0  # ciclos nao se sobrepoem
    for a, b in runs:
        a = max(a, free_from)
        shot_idx = next(
            (i for i, s in enumerate(shots) if s.start <= a < s.end), None
        )
        if shot_idx is None or shot_tracks[shot_idx] is None:
            continue
        shot = shots[shot_idx]
        if shot_idx > 0 and a < shot.start + SHOT_SETTLE_S:
            prev_cut = any(abs(c - shot.start) <= 0.3 for c in cuts)
            if not prev_cut:
                a = shot.start + SHOT_SETTLE_S
        # nada atravessa troca de cena nem troca de pessoa
        hard_end = min([shot.end, clip_end] + [c for c in cuts if c > a + 0.05])
        if b + MIN_LOCK_S > hard_end:
            # a fala atravessa uma troca de cena/pessoa: o zoom termina antes,
            # para a trava de 1 s caber no mesmo plano
            b = hard_end - LOCK_S
        if b - a < LONG_SPEECH_S:
            continue
        lock_end = b + LOCK_S
        nxt = next((s for s in starts if b + 0.05 < s <= b + LOCK_MAX_S), None)
        if nxt is not None and nxt > lock_end:
            lock_end = nxt
        lock_end = min(lock_end, hard_end)
        if lock_end - b < MIN_LOCK_S:
            continue
        zoom = zoom_for(b - a)
        if zoom < MIN_ZOOM:
            continue
        track = shot_tracks[shot_idx]
        face = _face_box(track, a, b, sample_fps)
        head = _head_path(track, a, lock_end, face[:2], sample_fps)
        beats.append(ZoomBeat(round(a, 3), round(b, 3), round(lock_end, 3),
                              round(zoom, 4), face, head))
        free_from = lock_end
    return beats


def _face_box(track, a: float, b: float, fps: float):
    boxes = [bx for i, bx in track.boxes.items() if a * fps - 1 <= i <= b * fps + 1]
    if not boxes:
        x, y, w, h = track.median_box()
        return (x + w / 2, y + h / 2, w, h)
    xs = sorted(bx[0] + bx[2] / 2 for bx in boxes)
    ys = sorted(bx[1] + bx[3] / 2 for bx in boxes)
    ws = sorted(bx[2] for bx in boxes)
    hs = sorted(bx[3] for bx in boxes)
    mid = len(boxes) // 2
    # tamanho: o maior (90o percentil) para a margem de seguranca valer
    top = min(len(boxes) - 1, int(len(boxes) * 0.9))
    return (xs[mid], ys[mid], ws[top], hs[top])


def _head_path(track, b: float, e: float, ref, fps: float):
    """Trilha suavizada do centro da cabeca em [b, e], relativa a `ref`."""
    pts = sorted(
        (i / fps, bx[0] + bx[2] / 2, bx[1] + bx[3] / 2)
        for i, bx in track.boxes.items()
        if b * fps - 2 <= i <= e * fps + 2
    )
    if len(pts) < 2:
        return []
    # media movel de 3 amostras: tira o tremido do detector
    smooth = []
    for k in range(len(pts)):
        win = pts[max(0, k - 1): k + 2]
        smooth.append((pts[k][0],
                       sum(p[1] for p in win) / len(win),
                       sum(p[2] for p in win) / len(win)))

    def at(t):
        if t <= smooth[0][0]:
            return smooth[0][1:]
        for (t0, x0, y0), (t1, x1, y1) in zip(smooth, smooth[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
        return smooth[-1][1:]

    times = [b] + [t for t, _x, _y in smooth if b < t < e] + [e]
    return [(round(t, 3), round(at(t)[0] - ref[0], 5), round(at(t)[1] - ref[1], 5))
            for t in times]
