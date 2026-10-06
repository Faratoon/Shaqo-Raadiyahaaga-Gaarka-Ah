#!/usr/bin/env bash
# ==============================================================================
# Shaqo Baahiye & Baahiye Bot (@Baahiyebot)
# Google Cloud Platform (GCP) - Always Free VM (e2-micro) Automated Setup
# ==============================================================================
set -e

echo "======================================================================="
echo "  🚀 Bilaabidda Diyaarinta Server-ka GCP Free Tier (e2-micro)"
echo "  Mashruuca: Shaqo Baahiye & @Baahiyebot"
echo "======================================================================="

# 1. Habeynta 2GB Swap Memory (Muhiim u ah 1GB RAM-ka e2-micro)
echo "[*] Hubinta iyo diyaarinta Swap Memory (2GB)..."
if ! grep -q '/swapfile' /proc/swaps; then
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "[✓] Swap memory 2GB si guul leh ayaa loo sameeyay!"
else
    echo "[✓] Swap memory horay ayaa loo diyaariyay."
fi

# 2. Cusboonaysiinta nidaamka & Shubbida Docker
echo "[*] Cusboonaysiinta xirmooyinka Ubuntu/Debian..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git ufw

echo "[*] Shubidda Docker & Docker Compose..."
if ! command -v docker &> /dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg || true
    sudo chmod a+r /etc/apt/keyrings/docker.gpg || true
    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "[✓] Docker si guul leh ayaa loo rakibay!"
else
    echo "[✓] Docker horay ayuu u rakibanaa."
fi

# 3. Furida Port-yada Firewall (UFW)
echo "[*] Habeynta Firewall-ka..."
sudo ufw allow 22/tcp || true
sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp || true
sudo ufw allow 5050/tcp || true
sudo ufw --force enable || true

# 4. Diyaarinta Mashruuca
PROJECT_DIR="$HOME/Shaqo-Raadiyahaaga-Gaarka-Ah"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "[*] Soo dejinta koodhka GitHub-ka..."
    git clone https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah.git "$PROJECT_DIR"
    cd "$PROJECT_DIR"
else
    echo "[*] Cusboonaysiinta koodhka..."
    cd "$PROJECT_DIR"
    git pull origin main || true
fi

# 5. Diyaarinta .env haddii aysan jirin
if [ ! -f ".env" ]; then
    echo "[*] Abuuridda faylka .env..."
    cat << 'EOF' > .env
TELEGRAM_BOT_TOKEN=8584246460:AAEuPrplHar3oiCyaM1E2cG-bLSgSOiXCRA
PORT=5050
EOF
    echo "[✓] Faylka .env waa la diyaariyay."
fi

# 6. Dhisidda iyo Kicinta Containers-ka Docker
echo "[*] Dhisidda iyo kicinta Docker Containers (Web Portal + Telegram Bot)..."
sudo docker compose down || true
sudo docker compose up -d --build

echo ""
echo "======================================================================="
echo "  🎉 HAMBALYO! Server-kii iyo Bot-kii si Live ah ayay u kaceen 24/7!"
echo "======================================================================="
echo "  • Telegram Bot: @Baahiyebot (Waa Live!)"
echo "  • Web Portal: http://$(curl -s ifconfig.me):5050"
echo "  • Status Check: sudo docker compose ps"
echo "  • Log-yada: sudo docker compose logs -f"
echo "======================================================================="
