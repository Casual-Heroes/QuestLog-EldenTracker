# -*- mode: python ; coding: utf-8 -*-
import shutil, os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'games.elden_ring',
        'games.elden_ring.bosses_vanilla',
        'games.elden_ring.bosses_dlc',
        'games.elden_ring.bosses_reforged',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'easyocr', 'torch', 'torchvision', 'torchaudio',
        'numpy', 'cv2', 'PIL', 'Pillow', 'mss',
        'matplotlib', 'scipy', 'sklearn',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QuestLog',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/CH.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QuestLog',
)

# Copy data folders next to the exe (not into _internal)
# core/paths.py looks for these relative to sys.executable
_dist = os.path.join(DISTPATH, 'QuestLog')
for _folder in ('overlay', 'games', 'assets'):
    _src = os.path.join(SPECPATH, _folder)
    _dst = os.path.join(_dist, _folder)
    if os.path.exists(_dst):
        shutil.rmtree(_dst)
    shutil.copytree(_src, _dst)
