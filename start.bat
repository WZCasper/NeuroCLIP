@echo off
chcp 65001 >nul
title NeuroClip

set PYTHON_CMD=

for /f %%i in ('python -c "print(1)" 2^>nul') do set PY_CHECK=%%i
if "%PY_CHECK%"=="1" set PYTHON_CMD=python
if defined PYTHON_CMD goto python_ok

set PY_CHECK=
for /f %%i in ('py -c "print(1)" 2^>nul') do set PY_CHECK=%%i
if "%PY_CHECK%"=="1" set PYTHON_CMD=py
if defined PYTHON_CMD goto python_ok

echo [ОШИБКА] Python не найден ^(или найдена только заглушка Windows Store^).
echo.
echo Установите настоящий Python 3.10 или новее с официального сайта:
echo https://www.python.org/downloads/
echo При установке ОБЯЗАТЕЛЬНО отметьте галочку "Add python.exe to PATH"
echo.
echo Если при запуске видите окно Microsoft Store - отключите заглушку:
echo Параметры Windows -^> Приложения -^> Дополнительные параметры приложений
echo -^> Псевдонимы выполнения приложений -^> выключите переключатели python.exe
echo.
pause
exit /b 1

:python_ok

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
