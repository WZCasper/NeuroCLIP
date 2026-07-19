# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для сборки NeuroClip в standalone .exe.

ВАЖНО: собирать нужно НА WINDOWS — PyInstaller не кросс-компилирует,
сборка на Linux/Mac даст исполняемый файл под ТУ ОС, где шёл билд,
не под Windows.

Запуск: pyinstaller neuroclip.spec  (или build_exe.bat)
Результат: dist/NeuroClip/ — ПАПКА, не один файл. CustomTkinter хранит
темы/шрифты как отдельные data-файлы, которые PyInstaller не может
корректно упаковать в --onefile (см. официальную документацию
CustomTkinter по паковке) — поэтому COLLECT ниже, а не --onefile.

console=True оставлен намеренно для первой сборки — если что-то пойдёт
не так при запуске .exe, вы увидите traceback в консоли вместо тихого
падения без единой подсказки. Когда всё заработает надёжно, можно
поменять на False для более опрятного вида без окна консоли.
"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Библиотеки со сложной структурой данных/бинарников — забираем целиком,
# а не перечисляем вручную: customtkinter (см. официальную доку по паковке,
# .json/.otf файлы иначе не подхватываются), mediapipe и librosa (нативные
# расширения + служебные data-файлы).
for package in ("customtkinter", "mediapipe", "librosa"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

# Собственные ресурсы проекта — шрифт неймплейта и (если есть) модель MediaPipe
datas += [("assets", "assets")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["PIL._tkinter_finder"],
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
    [],
    exclude_binaries=True,
    name="NeuroClip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NeuroClip",
)
