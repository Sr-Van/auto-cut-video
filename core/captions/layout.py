"""Agrupamento de palavras, quebra de linha e posicionamento geometrico."""

from __future__ import annotations

from core.captions.fonts import font_effective_size
from core.captions.models import CaptionBlock, CaptionWord
from core.options import ProcessingOptions


def words_in_window(
    segments, window_start: float, window_end: float
) -> list[CaptionWord]:
    """Extrai palavras do intervalo e rebaseia os tempos para comecar em 0."""
    result: list[CaptionWord] = []
    for seg in segments:
        for raw in getattr(seg, "words", None) or []:
            text = (getattr(raw, "text", "") or "").strip()
            if not text:
                continue
            if raw.end <= window_start or raw.start >= window_end:
                continue
            start = max(0.0, raw.start - window_start)
            end = max(0.0, min(raw.end, window_end) - window_start)
            if end <= start:
                end = start + 0.05
            result.append(CaptionWord(start=start, end=end, text=text))
    result.sort(key=lambda word: word.start)
    return result


def ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", "...", "…", ":", ";"))


def group_words(
    words: list[CaptionWord], options: ProcessingOptions
) -> list[CaptionBlock]:
    max_words = max(
        1, options.caption_max_words_per_line * options.caption_max_lines
    )
    blocks: list[CaptionBlock] = []
    current: list[CaptionWord] = []

    def flush():
        nonlocal current
        if current:
            blocks.append(
                CaptionBlock(
                    start=current[0].start, end=current[-1].end, words=current
                )
            )
            current = []

    for word in words:
        if current:
            gap = word.start - current[-1].end
            duration = word.end - current[0].start
            if (
                gap >= options.caption_gap_break
                or duration > options.caption_max_block_duration
                or len(current) >= max_words
            ):
                flush()
        current.append(word)
        if ends_sentence(word.text):
            flush()
    flush()
    return blocks


def display_text(text: str, options: ProcessingOptions) -> str:
    return text.upper() if options.caption_uppercase else text


def wrap_lines(
    words: list[CaptionWord], options: ProcessingOptions
) -> list[list[CaptionWord]]:
    per_line = max(1, options.caption_max_words_per_line)
    lines: list[list[CaptionWord]] = []
    line: list[CaptionWord] = []
    for word in words:
        if line and len(line) >= per_line:
            lines.append(line)
            line = []
        line.append(word)
    if line:
        lines.append(line)
    return lines


_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "no", "na", "nos", "nas", "em", "e", "ou", "que", "se", "por",
    "pra", "pro", "para", "com", "sem", "mas", "mais", "muito", "muita",
    "eu", "tu", "ele", "ela", "eles", "elas", "voce", "você", "vocês", "voces",
    "me", "te", "lhe", "nao", "não", "sim", "ja", "já", "tá", "ta", "é", "foi",
    "ser", "ter", "tem", "isso", "isto", "esse", "essa", "este", "esta",
    "aquele", "aquela", "aqui", "ali", "lá", "la", "quando", "como", "onde",
    "porque", "então", "entao", "também", "tambem", "assim", "meu", "minha",
    "seu", "sua", "nosso", "nossa", "ao", "aos", "à", "às", "pelo", "pela",
    "the", "and", "to", "of", "is", "it", "you",
}


def _core_word(text: str) -> str:
    return text.strip().strip(".,!?;:…\"'()[]").lower()


def keyword_index(words: list[CaptionWord]) -> int | None:
    """Escolhe a palavra-chave do bloco: numeros primeiro, senao a mais longa
    que nao seja stopword (min. 4 letras)."""
    best, best_score = None, 0.0
    for index, word in enumerate(words):
        core = _core_word(word.text)
        if not core or core in _STOPWORDS:
            continue
        if any(ch.isdigit() for ch in core):
            score = 100.0 + len(core)
        elif len(core) >= 4:
            score = float(len(core))
        else:
            continue
        if score > best_score:
            best, best_score = index, score
    return best


def is_support_word(text: str) -> bool:
    """Palavra de apoio (artigo, preposicao, pronome curto...): fica pequena."""
    core = _core_word(text)
    if not core:
        return True
    if any(ch.isdigit() for ch in core):
        return False
    return core in _STOPWORDS or len(core) <= 2


def mark_emphasis(blocks: list[CaptionBlock], options: ProcessingOptions) -> None:
    enabled = bool(getattr(options, "caption_emphasis", False))
    scale = float(getattr(options, "caption_emphasis_scale", 1.0) or 1.0)
    stairs = getattr(options, "caption_layout", "line") == "stairs"
    for block in blocks:
        if stairs and enabled:
            # Composicao: todas as palavras de conteudo grandes, as de apoio
            # pequenas; so a ultima palavra de conteudo da cena ganha cor.
            content = [i for i, w in enumerate(block.words) if not is_support_word(w.text)]
            chosen = content[-1] if content else None
            for index, word in enumerate(block.words):
                word.emphasis = index == chosen
                word.scale = scale if index in content else 1.0
            continue
        chosen = keyword_index(block.words) if enabled else None
        for index, word in enumerate(block.words):
            word.emphasis = index == chosen
            word.scale = scale if word.emphasis else 1.0


def layout_blocks(
    blocks: list[CaptionBlock],
    options: ProcessingOptions,
    canvas_w: int,
    canvas_h: int,
    font,
) -> list[CaptionBlock]:
    mark_emphasis(blocks, options)
    effective = font_effective_size(font, options.caption_font_size)
    base_line = effective * 1.35
    space = font.getlength(" ") * max(0.4, options.caption_word_spacing)
    if getattr(options, "caption_layout", "line") == "stairs":
        for block in blocks:
            _layout_stairs(block, options, canvas_w, canvas_h, font, effective)
        return blocks
    for block in blocks:
        lines = wrap_lines(block.words, options)
        # linhas com palavra ampliada ficam mais altas (entrelinha justa)
        row_scales = [max(w.scale for w in line) for line in lines]
        row_heights = [
            base_line + effective * (sc - 1.0) for sc in row_scales
        ]
        total_height = sum(row_heights)
        top = canvas_h - options.caption_margin_bottom - total_height
        y = top
        for line_words, row_scale, row_h in zip(lines, row_scales, row_heights):
            for w in line_words:
                w.width = font.getlength(display_text(w.text, options)) * w.scale
            line_width = sum(w.width for w in line_words) + space * max(
                0, len(line_words) - 1
            )
            x = (canvas_w - line_width) / 2
            for word in line_words:
                word.x = x
                # alinha a base: palavras menores descem o que a maior subiu
                word.y = y + effective * (row_scale - word.scale)
                x += word.width + space
            y += row_h
    return blocks


# Escada: linhas de ate 2 palavras (no maximo 1 grande), encavaladas (a
# seguinte cobre um pouco a anterior) e cada linha deslocada para a direita.
# Palavras de apoio ficam pequenas e alinhadas pelo topo da grande.
STAIRS_OVERLAP = 0.10  # fracao da altura da linha que invade a anterior
STAIRS_STEP = 0.9  # deslocamento horizontal por linha (em "em" da base)
STAIRS_GAP = 0.18  # espaco entre palavras da mesma linha (em "em" da base)


def stairs_rows(words: list[CaptionWord]) -> list[list[CaptionWord]]:
    """Agrupa: cada linha tem no maximo 2 palavras e no maximo 1 grande.
    "de recusar | um convite", "Paris pro | fashion | week?"."""
    rows: list[list[CaptionWord]] = []
    for word in words:
        big = word.scale > 1.01
        row = rows[-1] if rows else None
        if row is not None and len(row) < 2:
            row_has_big = any(w.scale > 1.01 for w in row)
            if not (big and row_has_big):
                row.append(word)
                continue
        rows.append([word])
    return rows


def _glyph_metrics(font, size: float) -> tuple[float, float]:
    """(linha de base, altura das letras altas) em px do canvas, por unidade
    de escala, do jeito que o libass posiciona com \\an7."""
    from core.captions.fonts import _win_metrics

    path = getattr(font, "path", None)
    metrics = _win_metrics(path) if path else None
    ascent_px, _descent_px = font.getmetrics()
    try:
        top = font.getbbox("hdlkA")[1]
    except Exception:
        top = ascent_px * 0.25
    ascender_h = max(1.0, ascent_px - top)
    if metrics:
        units, win_sum = metrics
        # win_ascent = (win_sum - win_descent); baseline fica a win_ascent do topo
        baseline_ratio = _win_ascent(path) / float(win_sum) if path else 0.75
    else:
        baseline_ratio = 0.75
    return size * baseline_ratio, ascender_h


def _win_ascent(path: str) -> float:
    import struct

    with open(path, "rb") as fh:
        data = fh.read()
    num_tables = struct.unpack(">H", data[4:6])[0]
    for i in range(num_tables):
        rec = data[12 + 16 * i : 28 + 16 * i]
        if rec[:4] == b"OS/2":
            off = struct.unpack(">I", rec[8:12])[0]
            return float(struct.unpack(">H", data[off + 74 : off + 76])[0])
    return 0.75


def _layout_stairs(block, options, canvas_w, canvas_h, font, effective) -> None:
    words = block.words
    if not words:
        return
    for w in words:
        w.width = font.getlength(display_text(w.text, options)) * w.scale
    base_off, _ascender_h = _glyph_metrics(font, options.caption_font_size)
    ascent_px = font.getmetrics()[0]

    def glyph_h(w: CaptionWord) -> float:
        """Altura visivel da palavra acima da linha de base (escala 1)."""
        try:
            top = font.getbbox(display_text(w.text, options))[1]
        except Exception:
            top = ascent_px * 0.3
        return max(1.0, ascent_px - top)

    step = effective * STAIRS_STEP
    gap = effective * STAIRS_GAP
    rows = stairs_rows(words)
    placed: list[tuple[CaptionWord, float, float]] = []  # (palavra, x, y)
    left = 0.0
    baseline = 0.0
    for r, row in enumerate(rows):
        row_scale = max(w.scale for w in row)
        big = [w for w in row if w.scale >= row_scale - 0.01]
        row_h = max(glyph_h(w) * w.scale for w in big)
        if r:
            left += step
            # o topo visivel desta linha invade um pouco a base da anterior
            baseline += row_h * (1.0 - STAIRS_OVERLAP)
        visible_top = baseline - row_h
        x = left
        for w in row:
            if w.scale >= row_scale - 0.01:
                y = baseline - base_off * w.scale  # grande: na linha de base
            else:
                # pequena: topo visivel alinhado ao topo visivel da grande
                y = visible_top - (base_off - glyph_h(w)) * w.scale
            placed.append((w, x, y))
            x += w.width + gap
    min_x = min(x for _, x, _ in placed)
    max_x = max(x + w.width for w, x, _ in placed)
    bottom = baseline + effective * max(w.scale for w in rows[-1]) * 0.3
    # mantem a composicao inteira dentro da tela (margem de 6%)
    margin = canvas_w * 0.06
    offset_x = (canvas_w - (max_x - min_x)) / 2 - min_x
    offset_x = max(margin - min_x, min(offset_x, canvas_w - margin - max_x))
    origin_y = canvas_h - options.caption_margin_bottom - bottom
    for w, x, y in placed:
        w.x = x + offset_x
        w.y = origin_y + y
