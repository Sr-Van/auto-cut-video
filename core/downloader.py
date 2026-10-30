from pathlib import Path
from threading import Event

import yt_dlp

from core.config import BASE_DIR
from core.exceptions import PipelineCancelledError, check_cancelled

OUTPUT_DIR = str(BASE_DIR / "temp")


def download_video(
    url: str,
    diretorio_saida: str = OUTPUT_DIR,
    progress_callback=None,
    cancel_event: Event | None = None,
) -> str | None:
    check_cancelled(cancel_event)

    last_percent = -1
    partial_files: set[str] = set()

    def _progress_hook(d):
        nonlocal last_percent
        filename = d.get("filename") or d.get("tmpfilename")
        if filename:
            partial_files.add(str(filename))

        check_cancelled(cancel_event)

        if progress_callback is None or d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if not total:
            return
        downloaded = d.get("downloaded_bytes") or 0
        percent = int(downloaded * 100 / total)
        if percent == last_percent:
            return
        last_percent = percent
        progress_callback("baixando", percent, "Baixando video...")

    ydl_opts = {
        "format": (
            "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=1080]/best"
        ),
        "paths": {
            "home": diretorio_saida,
            "temp": diretorio_saida,
        },
        "outtmpl": diretorio_saida + "/%(title)s.%(id)s.%(ext)s",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
        "progress_hooks": [_progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Extraindo informações e baixando: {url}...")
            info_dict = ydl.extract_info(url, download=True)
            check_cancelled(cancel_event)

            caminho_arquivo = ydl.prepare_filename(info_dict)
            caminho_arquivo = caminho_arquivo.rsplit(".", 1)[0] + ".mp4"
            print("caminho definido do arquivo: ", caminho_arquivo)
            return caminho_arquivo
    except PipelineCancelledError:
        _cleanup_partials(partial_files, diretorio_saida)
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            _cleanup_partials(partial_files, diretorio_saida)
            raise PipelineCancelledError() from e
        print(f"Erro ao baixar o vídeo: {e}")
        return None


def _cleanup_partials(partial_files: set[str], diretorio_saida: str) -> None:
    """Remove arquivos temporarios/parciais deixados por download interrompido."""
    for fpath in partial_files:
        for candidate in (Path(fpath), Path(f"{fpath}.part"), Path(f"{fpath}.ytdl")):
            try:
                if candidate.exists():
                    candidate.unlink()
            except OSError:
                pass
    out_dir = Path(diretorio_saida)
    if out_dir.exists():
        for ext in ("*.part", "*.ytdl"):
            for leftover in out_dir.glob(ext):
                try:
                    leftover.unlink()
                except OSError:
                    pass
