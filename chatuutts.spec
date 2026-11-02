# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

datas = [
    ("assets/mascot.gif", "assets"),
    ("assets/wordmark.png", "assets"),
    ("chatuutts.ico", "."),
    ("build/package-config", "config"),
    ("models/kokoro-int8-multi-lang-v1_1", "models/kokoro-int8-multi-lang-v1_1"),
]
binaries = []
hiddenimports = ["cffi"]

for package in ("pygame", "sounddevice", "miniaudio", "PIL", "pynput", "requests", "sherpa_onnx"):
    collected_datas, collected_binaries, collected_hidden = collect_all(package)
    datas += collected_datas
    binaries += collected_binaries
    hiddenimports += collected_hidden

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["cache"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CHATUUTTS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="chatuutts.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CHATUUTTS",
)
