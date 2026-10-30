"""Excecoes e utilitarios de cancelamento cooperativo do pipeline."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from threading import Event


class PipelineCancelledError(RuntimeError):
    """Lancada quando o usuario solicita o cancelamento do processamento."""

    def __init__(self, message: str = "Processamento cancelado pelo usuário."):
        super().__init__(message)


def check_cancelled(cancel_event: Event | None) -> None:
    """Verifica se o evento de cancelamento foi acionado."""
    if cancel_event is not None and cancel_event.is_set():
        raise PipelineCancelledError()


def sleep_with_cancel(seconds: float, cancel_event: Event | None = None) -> None:
    """Aguarda `seconds` interrompendo imediatamente caso `cancel_event` seja acionado."""
    if seconds <= 0:
        check_cancelled(cancel_event)
        return
    if cancel_event is None:
        import time

        time.sleep(seconds)
        return
    if cancel_event.wait(timeout=seconds):
        raise PipelineCancelledError()


def run_interruptible_cmd(
    cmd: list[str],
    *,
    cancel_event: Event | None = None,
    cwd: str | None = None,
    cleanup_path: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """Executa um subprocesso permitindo interrupcao imediata via `cancel_event`."""
    check_cancelled(cancel_event)

    if cancel_event is None:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=0.2)
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
            except subprocess.TimeoutExpired:
                if cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2.0)
                    if cleanup_path:
                        try:
                            if os.path.exists(cleanup_path):
                                os.remove(cleanup_path)
                        except OSError:
                            pass
                    raise PipelineCancelledError()
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2.0)
        raise

