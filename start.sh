#!/bin/bash

echo "[FunPay Analytics] Проверка виртуального окружения..."
if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение .venv..."
    python3 -m venv .venv
fi

echo "Активация окружения..."
source .venv/bin/activate

echo "Установка зависимостей..."
pip install -r requirements.txt

echo "Открытие браузера..."
if command -v xdg-open > /dev/null; then
  xdg-open http://localhost:5000 &
elif command -v open > /dev/null; then
  open http://localhost:5000 &
else
  echo "Пожалуйста, откройте вручную: http://localhost:5000"
fi

echo "Запуск сервера..."
python3 app.py
