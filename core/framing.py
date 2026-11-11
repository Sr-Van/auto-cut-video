"""Analise visual local para os formatos que seguem pessoas.

Roda 100% na maquina com OpenCV. Detector de rostos: YuNet (modelo de
~230 KB em core/models, licenca MIT; pega rosto de lado, com oculos ou mao
na frente); sem o modelo, cai para o Haar embutido. Para a janela de um corte:

1. Le ~4 frames/s em baixa resolucao direto do FFmpeg (pipe, tons de cinza).
2. Detecta rostos e agrupa em *trilhas* (a mesma pessoa ao longo do tempo).
3. Quem fala = trilha com mais movimento na regiao da boca enquanto o
   Whisper registra palavra naquele instante; planos com duracao minima
   evitam ficar pulando entre pessoas.
4. Webcam (react) = rosto pequeno e parado perto de uma borda.
5. Moldura de patrocinio (video encolhido + faixas fixas nas bordas) e
   detectada pelos pixels parados; nesses trechos a area viva e ampliada de
   volta para a tela cheia, entao o recorte nunca mostra a faixa.
6. O formato nunca muda dentro do corte: sem rosto, o recorte fica parado
   onde estava; cena inteira sem rosto usa o centro. Trocas de cena reais
   (detectadas nos mesmos frames) sao saltos secos; trocas de pessoa
   dentro da mesma cena deslizam.

Sem OpenCV/numpy, ou se nada for detectado, devolve um plano vazio e o
render cai para recorte central.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ALGO_VERSION = 5
SAMPLE_FPS = 4.0
ANALYSIS_WIDTH = 320
MIN_SHOT_S = 1.5
# Cena sem nenhum rosto por pelo menos isso usa o centro (e nao a ultima posicao).
MIN_FACELESS_S = 2.0
# Diferenca media (0-255) entre miniaturas 32x18 consecutivas que indica troca de cena.
SCENE_CUT_DIFF = 30.0
CENTER = -3  # indice especial de "centro da tela" nas escolhas por frame
# Moldura: janela (s) para medir pixels parados e grade da medicao.
LIVE_WINDOW_S = 3.0
LIVE_GRID = (64, 36)
MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
# SHA-256 do modelo oficial (opencv_zoo). Arquivo trocado/corrompido nao e carregado.
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

try:  # dependencias opcionais
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # noqa: BLE001
    cv2 = None
    np = None


def available() -> bool:
    return cv2 is not None and np is not None


Box = tuple[float, float, float, float]  # x, y, w, h normalizados (0-1)


@dataclass
class FocusShot:
    start: float
    end: float
    cx: float  # centro do rosto (0-1)
    cy: float
    size: float  # largura do rosto (0-1)


@dataclass
class FramingPlan:
    src_width: int = 0
    src_height: int = 0
    shots: list[FocusShot] = field(default_factory=list)
    cam_box: Box | None = None
    content_box: Box | None = None
    faces_found: int = 0
    scene_cuts: list[float] = field(default_factory=list)  # segundos, relativos
    # Trechos com moldura: (inicio, fim, caixa da area viva normalizada)
    live_boxes: list[tuple[float, float, Box]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FramingPlan":
        plan = cls(
            src_width=int(data.get("src_width", 0)),
            src_height=int(data.get("src_height", 0)),
            faces_found=int(data.get("faces_found", 0)),
        )
        plan.scene_cuts = [float(t) for t in data.get("scene_cuts", [])]
        keys = {"start", "end", "cx", "cy", "size"}
        plan.shots = [
            FocusShot(**{k: v for k, v in s.items() if k in keys})
            for s in data.get("shots", [])
        ]
        plan.live_boxes = [
            (float(a), float(b), tuple(float(v) for v in box))
            for a, b, box in data.get("live_boxes", [])
        ]
        cam = data.get("cam_box")
        plan.cam_box = tuple(cam) if cam else None
        content = data.get("content_box")
        plan.content_box = tuple(content) if content else None
        return plan


# --------------------------------------------------------------- leitura
def probe_size(video_path: str) -> tuple[int, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0, 0
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
        str(video_path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW
        ).stdout.strip()
        w, h = out.splitlines()[0].split("x")[:2]
        return int(w), int(h)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return 0, 0


def read_frames(video_path: str, start: float, end: float, src_w: int, src_h: int):
    """Frames em cinza a SAMPLE_FPS e ANALYSIS_WIDTH de largura."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not src_w or not src_h:
        return [], 0, 0
    aw = ANALYSIS_WIDTH
    ah = max(2, int(round(src_h * aw / src_w / 2)) * 2)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        # bidir: pula so os quadros B (~35% mais rapido, sem perder amostras)
        "-skip_frame", "bidir",
        "-ss", f"{start:.3f}", "-i", str(video_path),
        "-t", f"{max(0.1, end - start):.3f}",
        "-vf", f"fps={SAMPLE_FPS},scale={aw}:{ah}:flags=fast_bilinear",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        raw = subprocess.run(
            cmd, capture_output=True, timeout=300, creationflags=_NO_WINDOW
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return [], aw, ah
    size = aw * ah
    count = len(raw) // size
    frames = [
        np.frombuffer(raw, dtype=np.uint8, count=size, offset=i * size).reshape(ah, aw)
        for i in range(count)
    ]
    return frames, aw, ah


# ------------------------------------------------------------- deteccao
def scene_cuts(frames) -> list[int]:
    """Indices dos frames que comecam uma cena nova (corte seco/propaganda).

    Compara miniaturas 32x18 consecutivas: custo desprezivel perto da
    deteccao de rostos, e reaproveita os frames ja lidos.
    """
    cuts: list[int] = []
    prev = None
    for i, frame in enumerate(frames):
        small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_AREA).astype(np.int16)
        if prev is not None and float(np.abs(small - prev).mean()) > SCENE_CUT_DIFF:
            cuts.append(i)
        prev = small
    return cuts


_CASCADE = None


def _cascade():
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _CASCADE


_YUNET = {}
_MODEL_OK: bool | None = None


def _model_ok() -> bool:
    global _MODEL_OK
    if _MODEL_OK is None:
        import hashlib

        try:
            digest = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
        except OSError:
            digest = ""
        _MODEL_OK = digest == MODEL_SHA256
    return _MODEL_OK


def _yunet(w: int, h: int):
    if not hasattr(cv2, "FaceDetectorYN") or not _model_ok():
        return None
    det = _YUNET.get((w, h))
    if det is None:
        try:
            det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (w, h), 0.6, 0.3, 50)
        except cv2.error:
            return None
        _YUNET[(w, h)] = det
    return det


def has_yunet() -> bool:
    return available() and hasattr(cv2, "FaceDetectorYN") and _model_ok()


def detect_faces(frame) -> list[Box]:
    h, w = frame.shape[:2]
    det = _yunet(w, h)
    if det is not None:
        bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame
        _ok, found = det.detect(bgr)
        if found is None:
            return []
        out = []
        for row in found:
            x, y, fw, fh = (float(v) for v in row[:4])
            if fw > 2 and fh > 2:
                out.append((max(0.0, x) / w, max(0.0, y) / h, fw / w, fh / h))
        return out
    found = _cascade().detectMultiScale(
        cv2.equalizeHist(frame), scaleFactor=1.12, minNeighbors=5,
        minSize=(max(12, w // 28), max(12, w // 28)),
    )
    return [(x / w, y / h, fw / w, fh / h) for (x, y, fw, fh) in found]


@dataclass
class Track:
    boxes: dict[int, Box] = field(default_factory=dict)  # indice do frame -> caixa
    motion: dict[int, float] = field(default_factory=dict)

    def last_index(self) -> int:
        return next(reversed(self.boxes))  # boxes e preenchido em ordem crescente

    def last_center(self) -> tuple[float, float, float]:
        box = self.boxes[self.last_index()]
        return box[0] + box[2] / 2, box[1] + box[3] / 2, box[2]

    def median_box(self) -> Box:
        arr = np.array(list(self.boxes.values()))
        return tuple(float(v) for v in np.median(arr, axis=0))


def build_tracks(faces_per_frame: list[list[Box]], cuts=()) -> list[Track]:
    """Associa deteccoes por proximidade do centro (rastreador simples).

    Uma trilha nao atravessa troca de cena: um rosto da propaganda na mesma
    posicao nao herda a trilha de quem estava falando.
    """
    tracks: list[Track] = []
    cut_set = set(cuts)
    closed: list[Track] = []
    for idx, faces in enumerate(faces_per_frame):
        if idx in cut_set:
            closed.extend(tracks)
            tracks = []
        for box in faces:
            cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
            best, best_d = None, 1e9
            for tr in tracks:
                if idx - tr.last_index() > SAMPLE_FPS * 2:  # sumiu ha mais de 2 s
                    continue
                tx, ty, tw = tr.last_center()
                d = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
                if d < max(tw, box[2]) * 0.9 and d < best_d:
                    best, best_d = tr, d
            if best is None:
                best = Track()
                tracks.append(best)
            best.boxes[idx] = box
    tracks = closed + tracks
    # descarta deteccoes esporadicas (falsos positivos). O minimo vale por
    # cena: numa tomada aberta de 1 s da mesa, os rostos tem no maximo 4
    # acertos e mesmo assim precisam virar trilha.
    n = len(faces_per_frame)
    bounds = [0] + sorted(c for c in cut_set if 0 < c < n) + [n]
    base = max(3, min(int(n * 0.15), int(SAMPLE_FPS * 2)))

    def min_hits(track: Track) -> int:
        first = next(iter(track.boxes))
        for a, b in zip(bounds[:-1], bounds[1:]):
            if a <= first < b:
                return max(2, min(base, int((b - a) * 0.5)))
        return base

    return [t for t in tracks if len(t.boxes) >= min_hits(t)]


def mouth_motion(frames, tracks: list[Track]) -> None:
    """Energia de movimento no terco inferior de cada rosto (proxy de fala)."""
    if not frames:
        return
    h, w = frames[0].shape[:2]
    for tr in tracks:
        for idx, (x, y, bw, bh) in tr.boxes.items():
            if idx == 0:
                continue
            x0 = int((x + bw * 0.2) * w)
            x1 = int((x + bw * 0.8) * w)
            y0 = int((y + bh * 0.62) * h)
            y1 = int(min(1.0, y + bh * 1.02) * h)
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            a = frames[idx][y0:y1, x0:x1].astype(np.int16)
            b = frames[idx - 1][y0:y1, x0:x1].astype(np.int16)
            tr.motion[idx] = float(np.abs(a - b).mean())


# ----------------------------------------------------------- decisoes
def speech_mask(n_frames: int, words) -> list[bool]:
    mask = [False] * n_frames
    for word in words or []:
        a = int(float(word.start) * SAMPLE_FPS)
        b = int(float(word.end) * SAMPLE_FPS) + 1
        for i in range(max(0, a), min(n_frames, b)):
            mask[i] = True
    return mask


def choose_speakers(tracks: list[Track], n_frames: int, speaking: list[bool],
                    cuts=()) -> list[int]:
    """Indice da trilha em foco por frame (-1 = nenhum).

    Em cada troca de cena (ex.: o podcast abre para mostrar a mesa) a escolha
    recomeca: entre os rostos da cena nova, ganha quem mais mexe a boca nos
    proximos ~2 s (rosto de poster/quadro fica parado e perde); empate vai
    para o maior rosto.
    """
    cut_set = set(cuts)
    look = int(2 * SAMPLE_FPS)
    current = -1
    out = []
    for i in range(n_frames):
        if i in cut_set:
            current = -1
        present = [k for k, t in enumerate(tracks) if i in t.boxes]
        if not present:
            out.append(current)
            continue
        if current not in present:
            def score(k, i=i):
                tr = tracks[k]
                vals = [tr.motion.get(j, 0.0) for j in range(i, min(n_frames, i + look))
                        if j in tr.boxes and speaking[j]]
                return (sum(vals) / len(vals) if vals else 0.0, tr.boxes[i][2])

            current = max(present, key=score)
        if speaking[i] and len(present) > 1:
            scores = {k: tracks[k].motion.get(i, 0.0) for k in present}
            best = max(scores, key=scores.get)
            # histerese: so troca se mexer a boca claramente mais
            if scores[best] > scores.get(current, 0.0) * 1.35 + 0.4:
                current = best
        out.append(current)
    return out


def smooth_shots(choice: list[int], min_frames: int,
                 wide_min: int = 1) -> list[tuple[int, int, int]]:
    """Agrupa em planos (inicio, fim, trilha) com duracao minima."""
    runs: list[list[int]] = []
    for i, k in enumerate(choice):
        if runs and runs[-1][2] == k:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, k])
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for j, (a, b, k) in enumerate(runs):
            if b - a >= min_frames:
                continue
            # cena sem rosto ja passou pelo minimo proprio: mantem o centro
            if k == CENTER and b - a >= wide_min:
                continue
            # plano curto: incorpora ao vizinho mais longo
            left = runs[j - 1] if j > 0 else None
            right = runs[j + 1] if j + 1 < len(runs) else None
            target = max(
                (r for r in (left, right) if r is not None), key=lambda r: r[1] - r[0]
            )
            target[0] = min(target[0], a)
            target[1] = max(target[1], b)
            runs.pop(j)
            changed = True
            break
    merged: list[list[int]] = []
    for r in runs:
        if merged and merged[-1][2] == r[2]:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    return [tuple(r) for r in merged]


def find_cam(tracks: list[Track]) -> Box | None:
    """Rosto pequeno, estavel e perto de uma borda = webcam sobreposta."""
    best = None
    for tr in tracks:
        x, y, w, h = tr.median_box()
        cx, cy = x + w / 2, y + h / 2
        arr = np.array([(b[0] + b[2] / 2, b[1] + b[3] / 2) for b in tr.boxes.values()])
        steady = float(arr.std(axis=0).max()) < 0.03
        near_edge = min(cx, 1 - cx) < 0.3 or min(cy, 1 - cy) < 0.3
        if w < 0.22 and steady and near_edge:
            if best is None or len(tr.boxes) > len(best.boxes):
                best = tr
    if best is None:
        return None
    x, y, w, h = best.median_box()
    # a webcam costuma ter ~3x a largura do rosto e proporcao ~4:3
    cw = min(1.0, w * 3.2)
    ch = min(1.0, h * 3.0)
    cx, cy = x + w / 2, y + h / 2 + h * 0.25
    cx = min(max(cx, cw / 2), 1 - cw / 2)
    cy = min(max(cy, ch / 2), 1 - ch / 2)
    return (cx - cw / 2, cy - ch / 2, cw, ch)


def content_without_cam(cam: Box | None) -> Box:
    """Area de conteudo: tira a coluna da webcam se isso ainda deixa >= 65%."""
    if cam is None:
        return (0.0, 0.0, 1.0, 1.0)
    x, _y, w, _h = cam
    if x + w / 2 > 0.5 and x >= 0.65:
        return (0.0, 0.0, x, 1.0)
    if x + w / 2 <= 0.5 and (1 - (x + w)) >= 0.65:
        return (x + w, 0.0, 1 - (x + w), 1.0)
    return (0.0, 0.0, 1.0, 1.0)


def hold_positions(choice: list[int], tracks: list[Track], cuts=()) -> list[int]:
    """Sem formato alternativo: preenche os buracos sem trocar o enquadramento.

    - inicio sem deteccao usa o primeiro rosto encontrado;
    - cena inteira (entre trocas de cena) sem rosto por MIN_FACELESS_S ou
      mais usa o centro (CENTER); fora isso, o recorte fica onde estava.
    """
    out = list(choice)
    n = len(out)
    present = [any(i in t.boxes for t in tracks) for i in range(n)]
    bounds = [0] + sorted(c for c in set(cuts) if 0 < c < n) + [n]
    min_len = max(1, int(MIN_FACELESS_S * SAMPLE_FPS))
    prev = next((k for k in out if k >= 0), None)  # inicio usa o 1o rosto
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a >= min_len and not any(present[a:b]):
            for i in range(a, b):
                out[i] = CENTER
            continue
        # comeco da cena antes da 1a deteccao: usa o 1o rosto DESTA cena
        first = next((out[i] for i in range(a, b) if out[i] >= 0), prev)
        for i in range(a, b):
            if out[i] < 0 and first is not None:
                out[i] = first
            elif out[i] >= 0:
                first = out[i]
        prev = first
    return out


# -------------------------------------------------------------- moldura
def _strip(frac, n: int, step: float = 0.5) -> int:
    """Largura (em celulas) da faixa parada colada na borda, ou 0."""
    k = 0
    while k < n and frac[k] >= 0.97:
        k += 1
    if k < n * 0.06 or k > n * 0.45 or k >= n:
        return 0
    return k if frac[k] < step else 0  # degrau: dentro da faixa parado, fora mudou


def _live_box_of(stack) -> Box | None:
    gw, gh = LIVE_GRID
    still = stack.std(axis=0) < 2.0
    col = still.mean(axis=0)
    row = still.mean(axis=1)
    left = _strip(col, gw)
    right = _strip(col[::-1], gw)
    top = _strip(row, gh)
    bottom = _strip(row[::-1], gh)
    if not (left or right or top or bottom):
        return None
    box = (left / gw, top / gh, 1 - (left + right) / gw, 1 - (top + bottom) / gh)
    return box if box[2] >= 0.4 and box[3] >= 0.4 else None


def _outside_mask(box: Box):
    gw, gh = LIVE_GRID
    mask = np.ones((gh, gw), dtype=bool)
    x0, y0 = int(round(box[0] * gw)), int(round(box[1] * gh))
    x1, y1 = int(round((box[0] + box[2]) * gw)), int(round((box[1] + box[3]) * gh))
    mask[y0:y1, x0:x1] = False
    return mask


def live_boxes(frames, cuts=()) -> list[tuple[int, int, Box]]:
    """Trechos (ini, fim em frames) com moldura de patrocinio e a area viva.

    Parede de estudio com camera travada fica tao parada quanto um banner,
    entao pixel parado sozinho nao basta. O que separa os dois: o banner
    continua identico quando a CAMERA TROCA. Por isso:
    1. so procura faixas paradas em janelas que atravessam uma troca de cena;
    2. guarda a imagem da faixa como modelo;
    3. compara cada frame com o modelo para saber quando a moldura esta na tela.
    """
    n = len(frames)
    half = int(1.5 * SAMPLE_FPS)
    cut_list = sorted(c for c in set(cuts) if half <= c <= n - half)
    if not cut_list:
        return []
    small = np.array(
        [cv2.resize(f, LIVE_GRID, interpolation=cv2.INTER_AREA) for f in frames],
        dtype=np.float32,
    )
    models = []
    for c in cut_list:
        box = _live_box_of(small[c - half:c + half])
        if box is None:
            continue
        mask = _outside_mask(box)
        template = small[c - half:c + half].mean(axis=0)
        if not any(np.array_equal(mask, m) for _b, m, _t in models):
            models.append((box, mask, template))
    if not models:
        return []

    per: list = [None] * n
    for i in range(n):
        present = [
            box for box, mask, tpl in models
            if float(np.abs(small[i][mask] - tpl[mask]).mean()) < 6.0
        ]
        if present:
            x0 = max(b[0] for b in present)
            y0 = max(b[1] for b in present)
            x1 = min(b[0] + b[2] for b in present)
            y1 = min(b[1] + b[3] for b in present)
            per[i] = (x0, y0, x1 - x0, y1 - y0)

    spans: list[list] = []
    for i, box in enumerate(per):
        if box is None:
            continue
        if spans and i - spans[-1][1] <= 2 * SAMPLE_FPS:
            pbox = spans[-1][2]
            x0, y0 = max(pbox[0], box[0]), max(pbox[1], box[1])
            x1 = min(pbox[0] + pbox[2], box[0] + box[2])
            y1 = min(pbox[1] + pbox[3], box[1] + box[3])
            spans[-1][1] = i + 1
            spans[-1][2] = (x0, y0, x1 - x0, y1 - y0)
        else:
            spans.append([i, i + 1, box])
    spans = [s for s in spans if s[1] - s[0] >= SAMPLE_FPS]

    # A moldura entra animada (o video encolhe): durante a animacao o banner
    # ainda nao bate com o modelo, mas ela gera uma rajada de trocas de cena.
    # Recua o inicio ate a primeira troca dessa rajada (no maximo 3,5 s).
    all_cuts = sorted(set(cuts))
    limit = int(3.5 * SAMPLE_FPS)
    gap = int(2 * SAMPLE_FPS)
    out: list[tuple[int, int, Box]] = []
    for a, b, box in spans:
        start = a
        while True:
            prev = [c for c in all_cuts if start - gap <= c < start and a - c <= limit]
            if not prev:
                break
            start = min(prev)
        if out and start < out[-1][1]:
            start = out[-1][1]
        out.append((start, b, tuple(float(v) for v in box)))
    return out


def restore_geometry(live: Box, src_w: int, src_h: int) -> dict:
    """Recorte da area viva e ampliacao de volta para a tela cheia (px inteiros).

    Usado igual pela analise (para mapear rostos) e pelo render (filtro).
    """
    lx, ly, lw, lh = live
    cw = max(16, int(round(lw * src_w / 2)) * 2)
    ch = max(16, int(round(lh * src_h / 2)) * 2)
    cx = int(max(0, min(src_w - cw, round(lx * src_w))))
    cy = int(max(0, min(src_h - ch, round(ly * src_h))))
    s = max(src_w / cw, src_h / ch)
    sw = max(src_w, int(round(cw * s / 2)) * 2)
    sh = max(src_h, int(round(ch * s / 2)) * 2)
    ox, oy = (sw - src_w) // 2, (sh - src_h) // 2
    return {"cx": cx, "cy": cy, "cw": cw, "ch": ch, "sw": sw, "sh": sh, "ox": ox, "oy": oy}


def map_to_restored(box: Box, live: Box, src_w: int, src_h: int) -> Box:
    g = restore_geometry(live, src_w, src_h)
    kx, ky = g["sw"] / g["cw"], g["sh"] / g["ch"]
    x = ((box[0] * src_w - g["cx"]) * kx - g["ox"]) / src_w
    y = ((box[1] * src_h - g["cy"]) * ky - g["oy"]) / src_h
    return (x, y, box[2] * src_w * kx / src_w, box[3] * src_h * ky / src_h)


def plan_from_tracks(tracks, n_frames, words, src_w, src_h, want_cam: bool,
                     cuts=()) -> FramingPlan:
    plan = FramingPlan(src_width=src_w, src_height=src_h, faces_found=len(tracks))
    plan.scene_cuts = [c / SAMPLE_FPS for c in cuts]
    if want_cam:
        plan.cam_box = find_cam(tracks)
        plan.content_box = content_without_cam(plan.cam_box)
        # o rosto da webcam nao deve virar alvo do "seguir quem fala"
    candidates = tracks
    if plan.cam_box is not None:
        candidates = [t for t in tracks if t.median_box()[2] >= 0.22] or tracks
    if not candidates or n_frames == 0:
        return plan
    # Sem palavras com tempo (legenda desligada), considera fala o tempo todo.
    speaking = speech_mask(n_frames, words) if words else [True] * n_frames
    choice = choose_speakers(candidates, n_frames, speaking, cuts)
    choice = hold_positions(choice, candidates, cuts)
    # Troca de cena e limite rigido: a suavizacao roda dentro de cada cena,
    # entao uma tomada curta da mesa nao e engolida pelo plano vizinho.
    bounds = [0] + sorted(c for c in set(cuts) if 0 < c < n_frames) + [n_frames]
    runs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        for ra, rb, k in smooth_shots(choice[a:b], int(MIN_SHOT_S * SAMPLE_FPS),
                                      wide_min=max(1, int(MIN_FACELESS_S * SAMPLE_FPS))):
            if runs and runs[-1][2] == k and runs[-1][1] == a + ra:
                runs[-1] = (runs[-1][0], a + rb, k)
            else:
                runs.append((a + ra, a + rb, k))
    sizes = sorted(t.median_box()[2] for t in candidates)
    for a, b, k in runs:
        if k == CENTER:
            plan.shots.append(FocusShot(start=a / SAMPLE_FPS, end=b / SAMPLE_FPS,
                                        cx=0.5, cy=0.42, size=sizes[len(sizes) // 2]))
            continue
        if k < 0:
            continue
        x, y, w, h = candidates[k].median_box()
        plan.shots.append(
            FocusShot(start=a / SAMPLE_FPS, end=b / SAMPLE_FPS,
                      cx=x + w / 2, cy=y + h / 2, size=w)
        )

    if plan.shots:
        plan.shots[0].start = 0.0
        plan.shots[-1].end = max(plan.shots[-1].end, n_frames / SAMPLE_FPS)
    return plan


def _original_coords(tracks, lives, src_w, src_h):
    """Copia das trilhas com caixas de volta no frame original (para a boca)."""
    if not lives:
        return tracks
    inv: dict[int, Box] = {}
    for a, b, box in lives:
        for i in range(a, b):
            inv[i] = box
    out = []
    for tr in tracks:
        copy = Track()
        for i, bx in tr.boxes.items():
            live = inv.get(i)
            if live is None:
                copy.boxes[i] = bx
                continue
            g = restore_geometry(live, src_w, src_h)
            kx, ky = g["sw"] / g["cw"], g["sh"] / g["ch"]
            x = ((bx[0] * src_w + g["ox"]) / kx + g["cx"]) / src_w
            y = ((bx[1] * src_h + g["oy"]) / ky + g["cy"]) / src_h
            copy.boxes[i] = (x, y, bx[2] / kx, bx[3] / ky)
        out.append(copy)
    return out


# ---------------------------------------------------------------- API
def analyze_clip(video_path: str, start: float, end: float, words=None,
                 want_cam: bool = False, cache_path: Path | None = None,
                 cache_key: dict | None = None) -> FramingPlan:
    """Plano de enquadramento da janela [start, end] (tempos do plano sao relativos)."""
    key = dict(cache_key or {}, algo=ALGO_VERSION, want_cam=bool(want_cam))
    if cache_path is not None and cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("key") == key:
                return FramingPlan.from_dict(data["plan"])
        except (OSError, ValueError, KeyError, TypeError):
            pass

    src_w, src_h = probe_size(video_path)
    if not available():
        return FramingPlan(src_width=src_w, src_height=src_h)
    frames, _aw, _ah = read_frames(video_path, start, end, src_w, src_h)
    # YuNet e barato: detecta em todo frame. Haar (reserva) a cada 2 amostras.
    every = 1 if has_yunet() else 2
    faces = []
    for i, frame in enumerate(frames):
        faces.append(detect_faces(frame) if i % every == 0 or not faces else faces[-1])
    cuts = scene_cuts(frames)
    lives = live_boxes(frames, cuts) if not want_cam else []
    # Durante a moldura, rostos vao para as coordenadas da tela restaurada:
    # a mesma pessoa continua na mesma posicao quando a moldura entra/sai.
    for a, b, box in lives:
        for i in range(a, b):
            faces[i] = [map_to_restored(f, box, src_w, src_h) for f in faces[i]]
    tracks = build_tracks(faces, cuts)
    # o movimento da boca e medido no frame original
    originals = _original_coords(tracks, lives, src_w, src_h)
    mouth_motion(frames, originals)
    for tr, orig in zip(tracks, originals):
        tr.motion = orig.motion
    plan = plan_from_tracks(tracks, len(frames), words, src_w, src_h, want_cam, cuts)
    plan.live_boxes = [(a / SAMPLE_FPS, b / SAMPLE_FPS, box) for a, b, box in lives]
    if plan.live_boxes:
        a0, b0, box0 = plan.live_boxes[0]
        if a0 <= 1.0 / SAMPLE_FPS:
            plan.live_boxes[0] = (0.0, b0, box0)
        a1, b1, box1 = plan.live_boxes[-1]
        if b1 >= (len(frames) - 1) / SAMPLE_FPS:
            plan.live_boxes[-1] = (a1, max(b1, end - start + 1.0), box1)

    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"key": key, "plan": plan.to_dict()}), encoding="utf-8"
            )
        except OSError:
            pass
    return plan
