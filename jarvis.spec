from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "core" / "prompt.txt"), "core"),
    (str(ROOT / "core" / "face_model.obj"), "core"),
    (str(ROOT / "config" / "jarvis.ico"), "config"),
]
for folder_name in ("actions", "plugins", "dashboard"):
    folder = ROOT / folder_name
    datas.extend(
        (str(path), str(path.parent.relative_to(ROOT)))
        for path in folder.rglob("*")
        if path.is_file()
    )

hiddenimports = (
    collect_submodules("actions")
    + collect_submodules("plugins")
    + ["uvicorn.logging", "uvicorn.loops.auto"]
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "config" / "jarvis.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="Jarvis",
)
