# --- BLOCO DE INSTALAÇÃO (Execute uma vez) ---

# 1. Remove instalações quebradas anteriores
!apt-get remove chromium-chromedriver chromium-browser > /dev/null 2>&1

# 2. Instala dependências do sistema para o Chrome rodar
!apt-get update > /dev/null 2>&1
!apt-get install -y libgconf-2-4 libnss3-dev libgdk-pixbuf2.0-dev libgtk-3-dev libxss-dev libasound2 > /dev/null 2>&1

# 3. Baixa e instala o Google Chrome Stable Oficial
!wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
!dpkg -i google-chrome-stable_current_amd64.deb > /dev/null 2>&1
!apt-get -f install -y > /dev/null 2>&1 # Corrige dependências se falhar

# 4. Instala biblioteca Selenium
!pip install selenium gspread oauth2client > /dev/null 2>&1

print("✅ Ambiente configurado com Google Chrome Stable!")