import csv
import json
from pathlib import Path


def save_report(clips, output_dir, clip_paths=None):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, clip in enumerate(clips):
        row = dict(clip)
        if clip_paths and idx < len(clip_paths):
            row["file"] = clip_paths[idx]
        rows.append(row)

    json_path = out_dir / "relatorio.json"
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    csv_path = out_dir / "relatorio.csv"
    fieldnames = [
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
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return str(json_path)
