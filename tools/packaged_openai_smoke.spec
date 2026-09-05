# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


datas = []
binaries = []
hiddenimports = []
for package_name in (
    'pydantic',
    'pydantic_core',
    'annotated_types',
    'typing_inspection',
    'jiter',
):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package_name,
        on_error='warn once',
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    ['packaged_openai_smoke.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=['openai', 'openai._client'] + hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='packaged-openai-smoke',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
