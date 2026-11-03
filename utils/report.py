import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

from core.config import OUTPUT_DIR

PROJECTS_REGISTRY_FILENAME = "projetos.json"

CSV_FIELDNAMES = [
    "file",
    "start",
    "end",
    "hook",
    "category",
    "viral_score",
    "title",
    "description",
    "summary",
    "justification",
    "published",
]


def _write_report_files(rows: list[dict], out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "relatorio.json"
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    csv_path = out_dir / "relatorio.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return str(json_path)


def save_report(clips, output_dir, clip_paths=None):
    out_dir = Path(output_dir)

    rows = []
    for idx, clip in enumerate(clips):
        row = dict(clip)
        if clip_paths and idx < len(clip_paths):
            row["file"] = clip_paths[idx]
        row["published"] = bool(row.get("published", False))
        clip["published"] = row["published"]
        if "file" in row:
            clip["file"] = row["file"]
        rows.append(row)

    return _write_report_files(rows, out_dir)


def load_report(report_path: str | Path) -> list[dict]:
    path = Path(report_path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    item["published"] = bool(item.get("published", False))
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def update_clip_published(
    report_path: str | Path, clip_index: int, published: bool
) -> list[dict]:
    """Atualiza o campo `published` de um clipe no relatorio.json e relatorio.csv."""
    path = Path(report_path)
    rows = load_report(path)
    if 0 <= clip_index < len(rows):
        rows[clip_index]["published"] = bool(published)
        _write_report_files(rows, path.parent)
    return rows


def get_projects_registry_path(registry_path: str | Path | None = None) -> Path:
    if registry_path is not None:
        return Path(registry_path)
    return OUTPUT_DIR / PROJECTS_REGISTRY_FILENAME


def compute_average_viral_score(clips: list[dict]) -> float:
    """Soma de todas as notas dividida pelo numero de clips."""
    if not clips:
        return 0.0
    total = 0.0
    for clip in clips:
        try:
            total += float(clip.get("viral_score", 0) or 0)
        except (TypeError, ValueError):
            pass
    return round(total / len(clips), 2)


def load_projects_registry(registry_path: str | Path | None = None) -> list[dict]:
    """Carrega a lista de projetos ordenada do mais novo pro mais velho."""
    path = get_projects_registry_path(registry_path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            valid = [item for item in data if isinstance(item, dict)]
            valid.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
            return valid
    except (OSError, json.JSONDecodeError):
        pass
    return []


def save_projects_registry(
    projects: list[dict], registry_path: str | Path | None = None
) -> str:
    path = get_projects_registry_path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        [dict(p) for p in projects if isinstance(p, dict)],
        key=lambda p: str(p.get("created_at") or ""),
        reverse=True,
    )
    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(path)


def register_project(
    *,
    video_name: str,
    project_dir: str | Path,
    report_path: str | Path,
    clips: list[dict],
    clip_paths: list[str] | None = None,
    video_path: str | Path | None = None,
    yt_link: str | None = None,
    registry_path: str | Path | None = None,
) -> dict:
    """Registra ou atualiza um projeto finalizado no registro JSON (mais novo primeiro)."""
    proj_dir = Path(project_dir).resolve()
    rep_path = Path(report_path).resolve()
    now_iso = datetime.now().isoformat(timespec="seconds")

    clips_count = len(clips)
    avg_score = compute_average_viral_score(clips)

    entry = {
        "video_name": str(video_name or proj_dir.name),
        "clips_count": clips_count,
        "average_viral_score": avg_score,
        "created_at": now_iso,
        "project_dir": str(proj_dir),
        "report_path": str(rep_path),
        "video_path": str(video_path) if video_path else "",
        "yt_link": str(yt_link or ""),
        "clip_paths": [str(p) for p in (clip_paths or [])],
    }

    existing = load_projects_registry(registry_path)
    norm_target = str(proj_dir).lower()
    filtered = [
        item
        for item in existing
        if str(item.get("project_dir") or "").lower() != norm_target
    ]
    updated = [entry, *filtered]
    save_projects_registry(updated, registry_path)
    return entry


def delete_project(
    project_dir: str | Path,
    registry_path: str | Path | None = None,
) -> bool:
    """Exclui toda a pasta do projeto (e arquivos de vídeo associados) e remove do registro."""
    proj_dir = Path(project_dir)
    norm_target = str(proj_dir.resolve()).lower() if proj_dir.exists() else str(proj_dir).lower()

    existing = load_projects_registry(registry_path)
    matched_entries = []
    remaining = []
    for item in existing:
        item_dir = str(item.get("project_dir") or "")
        item_norm = (
            str(Path(item_dir).resolve()).lower()
            if item_dir and Path(item_dir).exists()
            else item_dir.lower()
        )
        if item_norm == norm_target or item_dir.lower() == str(proj_dir).lower():
            matched_entries.append(item)
        else:
            remaining.append(item)

    if proj_dir.exists() and proj_dir.is_dir():
        shutil.rmtree(proj_dir)

    # Se o video foi baixado diretamente na pasta pai (ex.: output/<video>.mp4), remove tambem
    for entry in matched_entries:
        if entry.get("yt_link"):
            vpath_str = entry.get("video_path") or ""
            if vpath_str:
                vpath = Path(vpath_str)
                try:
                    if vpath.is_file() and vpath.parent.resolve() == proj_dir.resolve().parent:
                        vpath.unlink()
                except OSError:
                    pass

    save_projects_registry(remaining, registry_path)
    return True
