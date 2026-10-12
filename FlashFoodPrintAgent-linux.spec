# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path.cwd()
hiddenimports = [
    "build_config",
    "uuid",
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "PIL",
    "PIL.Image",
    "customtkinter",
    "darkdetect",
]
hiddenimports += collect_submodules("customtkinter")
hiddenimports += collect_submodules("PIL")
datas = [
    (str(root / "assets"), "assets"),
    (str(root / "build_config.py"), "."),
] + collect_data_files("customtkinter")

a = Analysis(["agent.py"], pathex=[str(root)], binaries=[], datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FlashFoodPrintAgent", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name="FlashFoodPrintAgent")
