from pathlib import Path
from threading import Event

import os

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

    last_error: Exception | None = None
    try:
        for cookie_opts in _cookie_strategies():
            check_cancelled(cancel_event)
            try:
                with yt_dlp.YoutubeDL({**ydl_opts, **cookie_opts}) as ydl:
                    print(f"Extraindo informações e baixando: {url}... {cookie_opts or ''}")
                    info_dict = ydl.extract_info(url, download=True)
                    check_cancelled(cancel_event)

                    caminho_arquivo = ydl.prepare_filename(info_dict)
                    caminho_arquivo = caminho_arquivo.rsplit(".", 1)[0] + ".mp4"
                    _safe_print(f"caminho definido do arquivo: {caminho_arquivo}")
                    return caminho_arquivo
            except PipelineCancelledError:
                raise
            except Exception as e:
                if cancel_event is not None and cancel_event.is_set():
                    raise
                last_error = e
                if not _is_auth_error(e) and cookie_opts:
                    # falha ao ler cookies do navegador (ex.: nao instalado) -> tenta o proximo
                    continue
                if not _is_auth_error(e):
                    raise
                print("YouTube pediu autenticacao; tentando com cookies...")
        raise last_error or RuntimeError("Falha ao baixar o video")
    except PipelineCancelledError:
        _cleanup_partials(partial_files, diretorio_saida)
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            _cleanup_partials(partial_files, diretorio_saida)
            raise PipelineCancelledError() from e
        _safe_print(f"Erro ao baixar o vídeo: {e}")
        return None


COOKIES_FILE = BASE_DIR / "cookies.txt"
_BROWSERS = ("chrome", "firefox", "edge", "brave", "opera", "chromium")


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _is_auth_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "sign in" in msg or "not a bot" in msg or "cookies" in msg or "login" in msg


def _cookie_strategies():
    """Sem cookies primeiro; depois cookies.txt; depois cookies dos navegadores.

    Pode-se forcar via env: YTDLP_COOKIES=<arquivo> ou YTDLP_BROWSER=<navegador>.
    """
    yield {}
    env_file = os.environ.get("YTDLP_COOKIES")
    for f in (env_file, COOKIES_FILE):
        if f and Path(f).is_file():
            yield {"cookiefile": str(f)}
    env_browser = os.environ.get("YTDLP_BROWSER")
    browsers = (env_browser,) if env_browser else _BROWSERS
    for b in browsers:
        yield {"cookiesfrombrowser": (b,)}


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
