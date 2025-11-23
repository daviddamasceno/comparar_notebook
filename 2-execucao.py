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
    # Rola para garantir que o Lazy Load carregue tudo
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    
    cards = driver.find_elements(By.CSS_SELECTOR, "div.list_item")
    dados_locais = []
    
    for card in cards:
        try:
            # A. MODELO
            modelo = card.find_element(By.CSS_SELECTOR, "div.infos h4 a").get_attribute('innerText')
            
            # B. PREÇO (CORREÇÃO BRASIL)
            preco_texto = "0"
            try:
                # Tenta pegar preço verde
                preco_el = card.find_element(By.CSS_SELECTOR, ".buy-box .lowest-price a")
                preco_texto = preco_el.text
            except:
                try:
                    # Tenta pegar preço normal
                    preco_el = card.find_element(By.CSS_SELECTOR, ".buy-box .lowest-price-without-discounts p b")
                    preco_texto = preco_el.text
                except: pass
            
            # TRATAMENTO DO PREÇO (O Segredo)
            # 1. Tira o R$ e espaços
            p_limpo = preco_texto.replace("R$", "").strip()
            # 2. Tira o PONTO de milhar (3.529 vira 3529)
            p_limpo = p_limpo.replace(".", "")
            # 3. Troca a VÍRGULA decimal por PONTO (3529,99 vira 3529.99)
            p_limpo = p_limpo.replace(",", ".")
            
            # Converte para float apenas se tiver números
            if any(char.isdigit() for char in p_limpo):
                preco_float = float(p_limpo)
            else:
                preco_float = 0.0

            # C. CUPOM (CORREÇÃO DE LEITURA)
            cupom = ""
            try:
                # Busca TODOS os elementos de cupom dentro do card
                cupons_elements = card.find_elements(By.CSS_SELECTOR, ".coupon-code")
                for c in cupons_elements:
                    # textContent pega o texto mesmo se estiver oculto/overlay
                    texto_cupom = c.get_attribute("textContent").strip()
                    if texto_cupom:
                        cupom = texto_cupom
                        break # Achou um cupom válido, para de procurar
            except: 
                cupom = ""

            # D. SPECS
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
        except Exception as e:
            # print(f"Erro num card: {e}") # Descomente para debugar
            continue
            
    return dados_locais

# --- 4. EXECUÇÃO COM PAGINAÇÃO ---
base_url = "https://quenotebookcomprar.com.br/ofertas/?sort_order=_sfm_sale_lowest-price+asc+num&recomm=games-complex&_sfm_spec_laptop_category=Gamer&_sfm_spec_laptop_operating_system=Linux-%2B-Sem+sistema+operacional-%2B-Shell+EFI&post_types=notebooks"

print(f"Acessando Página 1: {base_url}")
driver.get(base_url)
time.sleep(4)

total_paginas = 1
try:
    texto_paginacao = driver.find_element(By.CSS_SELECTOR, "span.pages").text
    print(f"📄 {texto_paginacao}")
    match = re.search(r"de (\d+)", texto_paginacao)
    if match:
        total_paginas = int(match.group(1))
        print(f"🔢 Total de páginas detectadas: {total_paginas}")
except:
    print("⚠️ Paginação não encontrada, assumindo página única.")

todos_dados = []

for i in range(1, total_paginas + 1):
    if i > 1:
        proxima_url = f"{base_url}&sf_paged={i}"
        print(f"\n🔄 Indo para Página {i}...")
        driver.get(proxima_url)
        time.sleep(4)
    
    dados_pagina = extrair_dados_da_pagina(driver)
    todos_dados.extend(dados_pagina)
    print(f"📦 Página {i}: {len(dados_pagina)} itens extraídos.")

driver.quit()

# --- 5. SALVAR ---
if todos_dados:
    headers = ["Modelo", "Preço", "Cupom", "CPU", "GPU", "RAM", "Link"]
    worksheet.clear()
    worksheet.append_row(headers)
    worksheet.append_rows(todos_dados)
    
    # Formatação (Opcional)
    worksheet.format("B:B", {"numberFormat": {"type": "CURRENCY", "pattern": "R$ #,##0.00"}})
    
    print(f"\n✅ SUCESSO! {len(todos_dados)} notebooks salvos. Preços e cupons ajustados.")
else:
    print("❌ Nenhum dado encontrado.")