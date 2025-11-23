import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from google.colab import auth
import gspread
from google.auth import default
from thefuzz import process # Mágica para achar nomes parecidos
import time

# --- 1. CONFIGURAÇÕES E AUTH ---
print("Autenticando...")
auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

# Abre sua planilha
sh = gc.open('Notebooks_Scraper')
worksheet = sh.worksheet('Dados')

# Setup Selenium (Padrão)
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(options=options)

# --- 2. FUNÇÃO PARA BAIXAR TABELAS DO PASSMARK ---
def baixar_tabela_benchmark(url, tipo="CPU"):
    print(f"📥 Baixando base de dados de {tipo} do PassMark...")
    driver.get(url)
    time.sleep(5) # Espera tabela carregar
    
    dados = {}
    try:
        # A tabela do PassMark tem id 'cputable' ou 'gputable'
        # Vamos pegar todas as linhas da tabela
        rows = driver.find_elements(By.CSS_SELECTOR, "ul.chartlist li")
        
        for row in rows:
            try:
                # Nome do componente
                nome = row.find_element(By.CSS_SELECTOR, "span.prdname").text
                # Pontuação (Mark)
                score_text = row.find_element(By.CSS_SELECTOR, "span.count").text
                score = int(score_text.replace(",", ""))
                
                # Limpeza para melhorar o match (remove marcas registradas)
                nome_limpo = nome.replace("Intel", "").replace("AMD", "").replace("NVIDIA", "").strip()
                dados[nome_limpo] = score
            except:
                continue
    except Exception as e:
        print(f"Erro ao ler tabela: {e}")
        
    print(f"✅ {len(dados)} {tipo}s carregados na memória.")
    return dados

# --- 3. BAIXANDO AS BASES (HIGH END & MID RANGE) ---
# Precisamos das listas "High End" (Jogos) e talvez "Mid Range"
# CPU
cpu_db = baixar_tabela_benchmark("https://www.cpubenchmark.net/high_end_cpus.html", "CPU")
# GPU (High End)
gpu_db = baixar_tabela_benchmark("https://www.videocardbenchmark.net/high_end_gpus.html", "GPU")
# GPU (Mid Range - as vezes a 3050 cai aqui ou na High, melhor garantir)
gpu_db_mid = baixar_tabela_benchmark("https://www.videocardbenchmark.net/mid_range_gpus.html", "GPU_MID")
gpu_db.update(gpu_db_mid) # Junta tudo num dicionário só

driver.quit()

# --- 4. LENDO SUA PLANILHA ---
print("\n📖 Lendo seus notebooks...")
rows = worksheet.get_all_values()
headers = rows[0]
data = rows[1:]

# Descobre índices das colunas (para não depender da ordem fixa)
try:
    idx_cpu = headers.index("CPU")
    idx_gpu = headers.index("GPU")
    # Se não tiver colunas de Score, vamos criar nas posições seguintes
    if "Score CPU" not in headers:
        headers.extend(["Score CPU", "Score GPU", "Custo-Benefício"])
        worksheet.update('1:1', [headers]) # Atualiza cabeçalho
        idx_score_cpu = len(headers) - 3
        idx_score_gpu = len(headers) - 2
        idx_cb = len(headers) - 1
    else:
        idx_score_cpu = headers.index("Score CPU")
        idx_score_gpu = headers.index("Score GPU")
        idx_cb = headers.index("Custo-Benefício")
        
    idx_preco = headers.index("Preço")

except ValueError:
    print("❌ Erro: Colunas 'CPU', 'GPU' ou 'Preço' não encontradas.")
    raise

# --- 5. O GRANDE LOOP DE ATUALIZAÇÃO ---
print("\n🔍 Cruzando dados (Isso pode demorar um pouco)...")

novos_dados = []
lista_cpus_passmark = list(cpu_db.keys())
lista_gpus_passmark = list(gpu_db.keys())

for row in data:
    # Garante que a linha tenha tamanho suficiente para receber novos dados
    while len(row) < len(headers):
        row.append("")
        
    notebook_cpu = row[idx_cpu]
    notebook_gpu = row[idx_gpu]
    preco = float(row[idx_preco]) if row[idx_preco] else 1.0 # Evita div por zero
    
    # --- MATCHING CPU ---
    score_cpu = 0
    if notebook_cpu and notebook_cpu != "N/A":
        # Limpeza leve
        busca = notebook_cpu.replace("Intel", "").replace("AMD", "").replace("Core", "").strip()
        # TheFuzz: Acha o nome mais parecido na lista do PassMark
        # scorer=process.fuzz.token_set_ratio ajuda quando a ordem das palavras muda
        melhor_match, nota_match = process.extractOne(busca, lista_cpus_passmark)
        
        if nota_match > 80: # Se tiver 80% de certeza
            score_cpu = cpu_db[melhor_match]
            # print(f"CPU: {busca} -> {melhor_match} ({score_cpu})")
        else:
            print(f"⚠️ CPU não encontrada: {notebook_cpu}")

    # --- MATCHING GPU ---
    score_gpu = 0
    if notebook_gpu and notebook_gpu != "N/A":
        # GPUs de notebook geralmente têm "Laptop GPU" ou "Mobile" no PassMark
        busca = notebook_gpu.replace("NVIDIA", "").replace("GeForce", "").replace("Dedicada", "").strip()
        
        # Truque: Tentar achar primeiro com sufixo "Laptop GPU"
        matches = process.extract(busca + " Laptop GPU", lista_gpus_passmark, limit=3)
        # Pega o melhor
        melhor_match = matches[0][0]
        nota_match = matches[0][1]
        
        if nota_match > 75:
            score_gpu = gpu_db[melhor_match]
            # print(f"GPU: {busca} -> {melhor_match} ({score_gpu})")
        else:
            print(f"⚠️ GPU não encontrada: {notebook_gpu}")

    # --- CALCULA SCORE CUSTO BENEFÍCIO ---
    # Fórmula: (CPU*0.4 + GPU*0.6) / Preço
    if preco > 100:
        pontos_totais = (score_cpu * 0.4) + (score_gpu * 0.6)
        cb_score = round(pontos_totais / preco, 4) * 1000 # Multipliquei por 1000 pra ficar legível (ex: 8.5)
    else:
        cb_score = 0

    # Atualiza a linha
    row[idx_score_cpu] = score_cpu
    row[idx_score_gpu] = score_gpu
    row[idx_cb] = cb_score
    
    novos_dados.append(row)

# --- 6. SALVA TUDO DE VOLTA ---
print("\n💾 Salvando notas na planilha...")
worksheet.update(range_name=f'A2', values=novos_dados)
print("✅ Concluído! Verifique as colunas Score CPU, Score GPU e Custo-Benefício.")