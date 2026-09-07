# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files


sdk_datas = collect_data_files('PyQt5', includes=['**/translations/qtbase_ja.qm', '**/translations/qtbase_zh_CN.qm'])
sdk_binaries = []
sdk_hiddenimports = []
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
    sdk_datas += package_datas
    sdk_binaries += package_binaries
    sdk_hiddenimports += package_hiddenimports

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=sdk_binaries,
    datas=[
        ('resources/config.default.json', '.'),
        ('resources/locales', 'resources/locales'),
        ('resources/pattern_library.json', '.'),
        ('resources/plc_models.json', '.'),
        ('resources/instructions/mitsubishi', 'resources/instructions/mitsubishi'),
        ('README.md', '.'),
        ('resources/app.ico', '.'),
        ('resources/assets/codicons', 'assets/codicons'),
        ('resources/knowledge/fx3u_knowledge.sqlite', 'knowledge'),
        ('resources/knowledge/fx3u_dense_lsa.npz', 'knowledge'),
        ('resources/knowledge/manifest.json', 'knowledge'),
        # workbench_widgets is now a package facade; the historical module is
        # loaded as the editor engine at runtime and therefore must remain as data.
        ('src/workbench_widgets.py', '.'),
    ] + sdk_datas,
    hiddenimports=[
        'openai',
        'openai._client',
        'pywinauto',
        'pywinauto.controls.uia_controls',
        'comtypes.client',
        'numpy',
    ] + sdk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'xmlrpc', 'pydoc', 'PyQt6'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GXWorks2-ST-Ladder-Helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/app.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GXWorks2-ST-Ladder-Helper',
)
