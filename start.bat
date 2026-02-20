@echo off
chcp 65001 >nul
title FunPay Analytics Launcher

echo [FunPay Analytics] Проверка виртуального окружения...
if not exist ".venv" (
    echo Создаю виртуальное окружение .venv...
    python -m venv .venv
)

echo Активация окружения...
call .venv\Scripts\activate.bat

echo Установка зависимостей...
pip install -r requirements.txt

echo Открытие браузера...
start http://localhost:5000

echo Запуск сервера...
python app.py

pause
