@echo off
chcp 65001 >nul
title NeuroClip - Сборка exe

if not exist venv\Scripts\activate.bat (
    echo [ОШИБКА] Сначала запустите start.bat хотя бы раз - нужно окружение с зависимостями.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
pip install --quiet pyinstaller
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить pyinstaller.
    pause
    exit /b 1
)

echo Собираю NeuroClip.exe - это может занять несколько минут...
pyinstaller --noconfirm neuroclip.spec
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сборка не удалась - текст ошибки выше.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Готово! Результат: dist\NeuroClip\NeuroClip.exe
echo   Переносить нужно ВСЮ папку dist\NeuroClip,
echo   не только .exe - в ней все необходимые файлы.
echo ============================================
pause
