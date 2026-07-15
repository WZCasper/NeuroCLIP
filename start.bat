@echo off
chcp 65001 >nul
title NeuroClip

set PYTHON_CMD=python
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo [ОШИБКА] Python не найден.
        echo.
        echo Установите Python 3.10 или новее:
        echo https://www.python.org/downloads/
        echo При установке ОБЯЗАТЕЛЬНО отметьте галочку "Add python.exe to PATH"
        echo.
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
)

if not exist venv\Scripts\activate.bat (
    echo ============================================
    echo   Первый запуск - устанавливаю NeuroClip
    echo   Это займёт несколько минут, подождите...
    echo ============================================
    echo.

    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )

    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ОШИБКА] Не удалось установить зависимости - текст ошибки выше.
        pause
        exit /b 1
    )

    if not exist .env (
        copy .env.example .env >nul
        echo.
        echo Создан файл .env - откройте его в блокноте и впишите токен
        echo Telegram-бота, когда он понадобится ^(см. README.md^).
    )

    echo.
    echo Установка завершена. Запускаю NeuroClip...
    echo.
) else (
    call venv\Scripts\activate.bat
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] ffmpeg не найден - анализ звука работать не будет.
    echo Остальное это не затронет. Скачать: https://ffmpeg.org/download.html
    echo.
)

python main.py

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Программа завершилась с ошибкой ^(текст выше^).
    pause
)
