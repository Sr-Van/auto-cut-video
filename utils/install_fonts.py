"""Instala as fontes de assets/fonts para o usuario atual do Windows.

O app nao precisa disso para renderizar (ele usa as fontes da pasta
assets/fonts direto), mas instalar deixa Poppins/Montserrat disponiveis em
outros programas (CapCut, Photoshop, navegador...).

Instalacao por usuario: copia para %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts e
registra em HKCU, sem precisar de administrador.

Uso:  python -m utils.install_fonts
"""

from __future__ import annotations

import os
import shutil
import sys

from core.captions.fonts import bundled_font_files

_REG_PATH = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"


def _display_name(path: str) -> str:
    from PIL import ImageFont

    family, style = ImageFont.truetype(path, 16).getname()
    suffix = "" if (style or "").lower() == "regular" else f" {style}"
    return f"{family}{suffix} (TrueType)"


def install_user_fonts() -> list[str]:
    if sys.platform != "win32":
        raise RuntimeError("Instalacao automatica so no Windows.")
    import ctypes
    import winreg

    target_dir = os.path.join(
        os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts"
    )
    os.makedirs(target_dir, exist_ok=True)
    installed: list[str] = []
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
        for src in bundled_font_files():
            dest = os.path.join(target_dir, os.path.basename(src))
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
            winreg.SetValueEx(key, _display_name(src), 0, winreg.REG_SZ, dest)
            ctypes.windll.gdi32.AddFontResourceW(dest)
            installed.append(os.path.basename(src))
    # avisa os programas abertos que a lista de fontes mudou
    HWND_BROADCAST, WM_FONTCHANGE = 0xFFFF, 0x001D
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0x0002, 1000, None
    )
    return installed


if __name__ == "__main__":
    for name in install_user_fonts():
        print("instalada:", name)
