from utils.timefmt import hhmmss_to_seconds, seconds_to_hhmmss


def compute_cut_points(segments, total_duration, pause_gap):
    points = [0.0, total_duration]
    for i in range(len(segments) - 1):
        gap = segments[i + 1].start - segments[i].end
        if gap >= pause_gap:
            points.append((segments[i].end + segments[i + 1].start) / 2)
    return sorted(points)


def _snap(value, cut_points):
    return min(cut_points, key=lambda p: abs(p - value))


def _expand(s, e, hook, total, min_duration):
    if e - s >= min_duration:
        return s, e

    half = min_duration / 2
    ns = min(s, hook - half)
    ne = max(e, hook + half)

    ns = max(0.0, ns)
    ne = min(total, ne)

    if ne - ns < min_duration:
        room_left = ns
        room_right = total - ne
        if room_left >= room_right:
            ns = max(0.0, ne - min_duration)
        else:
            ne = min(total, ns + min_duration)

    return ns, ne


def _shrink(s, e, hook, total, max_duration):
    half = max_duration / 2
    ns = max(s, hook - half)
    ne = min(e, hook + half)
    ns = min(ns, hook)
    ne = max(ne, hook)
    return ns, ne


def _snap_end(ne, ns, cut_points, min_duration, max_duration, total):
    cand = _snap(ne, cut_points)
    cand = max(cand, ns + min_duration)
    cand = min(cand, ns + max_duration, total)
    return cand


def normalize_clips(clips, segments, total_duration, min_duration, max_duration, pause_gap):
    cut_points = compute_cut_points(segments, total_duration, pause_gap)

    expanded = []
    for clip in clips:
        s = hhmmss_to_seconds(clip["start"])
        e = hhmmss_to_seconds(clip["end"])
        hook = hhmmss_to_seconds(clip.get("hook", clip["start"]))

        ns, ne = _expand(s, e, hook, total_duration, min_duration)
        if ne - ns > max_duration:
            ns, ne = _shrink(ns, ne, hook, total_duration, max_duration)

        ne = _snap_end(ne, ns, cut_points, min_duration, max_duration, total_duration)
        if ne <= ns:
            ne = min(total_duration, ns + min_duration)

        entry = dict(clip)
        entry["_s"] = ns
        entry["_e"] = ne
        expanded.append(entry)

    expanded.sort(key=lambda c: c["_s"])

    merged = []
    for entry in expanded:
        if merged and entry["_s"] <= merged[-1]["_e"]:
            last = merged[-1]
            last["_e"] = max(last["_e"], entry["_e"])
            if entry.get("viral_score", 0) > last.get("viral_score", 0):
                for key, value in entry.items():
                    if key in ("start", "end", "_s", "_e"):
                        continue
                    last[key] = value
        else:
            merged.append(entry)

    result = []
    for entry in merged:
        clip = {k: v for k, v in entry.items() if k not in ("_s", "_e")}
        clip["start"] = seconds_to_hhmmss(entry["_s"])
        clip["end"] = seconds_to_hhmmss(entry["_e"])
        result.append(clip)

    return result
