#!/bin/bash

# ArchiMemo - Скрипт за лесна инсталация на Linux Mint / Ubuntu / Debian
# Този скрипт ще настрои автоматичен старт и рестарт на сървъра.

echo "🚀 Започвам настройка на ArchiMemo..."

# 1. Проверка за Python и venv
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не е намерен. Инсталирайте го: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

# 2. Създаване на virtual environment
echo "🐍 Създавам virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 3. Инсталиране на зависимости
echo "📦 Инсталирам Python зависимости в venv..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Създаване на необходимите директории
echo "📁 Създавам директории за данни и сигурност..."
mkdir -p data
mkdir -p secure

# 5. Генериране на systemd service файл
echo "⚙️ Генерирам systemd service..."

USER_NAME=$(whoami)
APP_DIR=$(pwd)
PYTHON_PATH="$APP_DIR/venv/bin/python3"

SERVICE_FILE="/etc/systemd/system/archmemo.service"

# Използваме template-а за да създадем финалния файл
sed -e "s|{{USER}}|$USER_NAME|g" \
    -e "s|{{APP_DIR}}|$APP_DIR|g" \
    -e "s|{{PYTHON_PATH}}|$PYTHON_PATH|g" \
    archmemo.service.template > archmemo.service

echo "📝 Копирам service файла в /etc/systemd/system/ (ще бъде поискана парола)..."
sudo cp archmemo.service $SERVICE_FILE

# 6. Стартиране на услугата
echo "🔄 Стартирам и активирам услугата..."
sudo systemctl daemon-reload
sudo systemctl enable archmemo.service
sudo systemctl restart archmemo.service

echo ""
echo "🔐 --- ВАЖНО: Пароли и Аутентикация ---"
echo "След като скриптът приключи, трябва да копирате тези файлове от стария компютър:"
echo ""
echo "1. OneDrive Token (от стария компютър):"
echo "   scp user@old-ip:~/.onedrive_business_token_cache.json ./secure/onedrive_token_cache.json"
echo ""
echo "2. SMTP Credentials (от стария компютър):"
echo "   scp user@old-ip:~/.archmemo/.secure/credentials.ini ./secure/credentials.ini"
echo ""
echo "Или ако използвате USB/друг метод — поставете файловете в папката secure/
echo "---------------------------------------"
echo ""
echo "✅ ArchiMemo е настроен и стартиран!"
echo "📍 Сървърът е достъпен на: http://localhost:5000"
echo "📊 Можете да проверите статуса с: sudo systemctl status archmemo.service"
echo "📜 Можете да видите лога с: tail -f app.log"
