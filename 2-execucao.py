import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from google.colab import auth
import gspread
from google.auth import default
import time
import re

# --- 1. AUTENTICAÇÃO ---
print("Autenticando no Google...")
try:
    auth.authenticate_user()
    creds, _ = default()
    gc = gspread.authorize(creds)
    sh = gc.open('Notebooks_Scraper')
    worksheet = sh.worksheet('Dados')
except Exception as e:
    print(f"❌ Erro na planilha: {e}")
    raise e

# --- 2. CONFIGURAÇÃO DO CHROME ---
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--remote-debugging-port=9222')
options.add_argument('--window-size=1920,1080')
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

driver = webdriver.Chrome(options=options)

# --- 3. FUNÇÃO DE EXTRAÇÃO (Reutilizável para cada página) ---
def extrair_dados_da_pagina(driver):
    # Rola um pouco para garantir carregamento de imagens (lazy load)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    
    cards = driver.find_elements(By.CSS_SELECTOR, "div.list_item")
    dados_locais = []
    
    for card in cards:
        try:
            # Modelo
            modelo = card.find_element(By.CSS_SELECTOR, "div.infos h4 a").get_attribute('innerText')
            
            # Preço
            preco_float = 0.0
            try:
                preco_el = card.find_element(By.CSS_SELECTOR, ".buy-box .lowest-price a")
                preco_texto = preco_el.text
            except:
                try:
                    preco_el = card.find_element(By.CSS_SELECTOR, ".buy-box .lowest-price-without-discounts p b")
                    preco_texto = preco_el.text
                except: preco_texto = "0"
            
            preco_limpo = ''.join(c for c in preco_texto if c.isdigit() or c == '.')
            preco_float = float(preco_limpo) if preco_limpo else 0.0

            # Cupom
            try: cupom = card.find_element(By.CSS_SELECTOR, ".coupon-code").text
            except: cupom = ""

            # CPU/GPU/RAM
            try: cpu = card.find_element(By.CSS_SELECTOR, ".spec_stamp.cpu span").get_attribute('innerText').replace("\n", " ")
            except: cpu = "N/A"
            try: gpu = card.find_element(By.CSS_SELECTOR, ".spec_stamp.gpu span").get_attribute('innerText').replace("\n", " ").replace("Dedicada", "").replace("GeForce", "").strip()
            except: gpu = "N/A"
            ram = "N/A"
            try:
                specs = card.find_elements(By.CSS_SELECTOR, ".spec_stamps.mobile span.spec_mobile")
                for s in specs:
                    txt = s.get_attribute('innerText')
                    if ("RAM" in txt or "GB" in txt) and "SSD" not in txt:
                        ram = txt; break
            except: pass

            link = card.find_element(By.CSS_SELECTOR, "div.infos h4 a").get_attribute("href")
            
            dados_locais.append([modelo, preco_float, cupom, cpu, gpu, ram, link])
        except:
            continue
    return dados_locais

# --- 4. LÓGICA DE PAGINAÇÃO AUTOMÁTICA ---
base_url = "https://quenotebookcomprar.com.br/ofertas/?sort_order=_sfm_sale_lowest-price+asc+num&recomm=games-complex&_sfm_spec_laptop_category=Gamer&_sfm_spec_laptop_operating_system=Linux-%2B-Sem+sistema+operacional-%2B-Shell+EFI&post_types=notebooks"

print(f"Acessando Página 1: {base_url}")
driver.get(base_url)
time.sleep(3)

# Descobre o total de páginas
total_paginas = 1
try:
    # Busca o texto "Página 1 de 3"
    texto_paginacao = driver.find_element(By.CSS_SELECTOR, "span.pages").text
    print(f"📄 Informação encontrada: {texto_paginacao}")
    
    # Extrai o último número do texto (ex: "3")
    match = re.search(r"de (\d+)", texto_paginacao)
    if match:
        total_paginas = int(match.group(1))
        print(f"🔢 Total de páginas detectadas: {total_paginas}")
except:
    print("⚠️ Paginação não encontrada, assumindo página única.")

# --- 5. LOOP PRINCIPAL ---
todos_dados = []

# Loop de 1 até total_paginas
for i in range(1, total_paginas + 1):
    if i > 1:
        # Se não for a página 1, constrói a URL da página X
        # O padrão do site é adicionar &sf_paged=NUMERO no final
        proxima_url = f"{base_url}&sf_paged={i}"
        print(f"\n🔄 Navegando para Página {i}: {proxima_url}")
        driver.get(proxima_url)
        time.sleep(3)
    
    print(f"Extraindo dados da página {i}...")
    dados_pagina = extrair_dados_da_pagina(driver)
    todos_dados.extend(dados_pagina)
    print(f"📦 +{len(dados_pagina)} itens coletados.")

driver.quit()

# --- 6. SALVAR ---
if todos_dados:
    headers = ["Modelo", "Preço", "Cupom", "CPU", "GPU", "RAM", "Link"]
    worksheet.clear()
    worksheet.append_row(headers)
    worksheet.append_rows(todos_dados)
    worksheet.format("B:B", {"numberFormat": {"type": "CURRENCY", "pattern": "R$ #,##0.00"}})
    print(f"\n✅ SUCESSO TOTAL! {len(todos_dados)} notebooks salvos na planilha.")
else:
    print("❌ Nenhum dado encontrado.")