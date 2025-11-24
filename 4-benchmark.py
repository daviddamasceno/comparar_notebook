import pandas as pd
import requests
from bs4 import BeautifulSoup
from google.colab import auth
import gspread
from google.auth import default
from thefuzz import process
import time

# --- 1. AUTENTICAÇÃO ---
print("Autenticando no Google...")
auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

# Abre sua planilha
try:
    sh = gc.open('Notebooks_Scraper')
    worksheet = sh.worksheet('Dados')
except Exception as e:
    print(f"❌ Erro ao abrir planilha: {e}")
    raise e

# --- 2. FUNÇÃO OTIMIZADA (SEM SELENIUM) ---
def baixar_tabela_benchmark_rapido(url, tipo="CPU"):
    print(f"📥 Baixando dados de {tipo} via Requests (Modo Turbo)...")
    
    # Cabeçalho para fingir ser um navegador (evita bloqueio 403)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code != 200:
            print(f"⚠️ Erro ao acessar {url}: Status {response.status_code}")
            return {}
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        dados = {}
        # O seletor do PassMark geralmente é uma lista 'chartlist'
        rows = soup.select("ul.chartlist li")
        
        for row in rows:
            try:
                # Nome: span com classe prdname
                nome_el = row.select_one("span.prdname")
                # Score: span com classe count
                score_el = row.select_one("span.count")
                
                if nome_el and score_el:
                    nome = nome_el.get_text(strip=True)
                    score_texto = score_el.get_text(strip=True).replace(",", "")
                    score = int(score_texto)
                    
                    # Limpeza para melhorar o match
                    nome_limpo = nome.replace("Intel", "").replace("AMD", "").replace("NVIDIA", "").strip()
                    dados[nome_limpo] = score
            except:
                continue
                
        print(f"✅ {len(dados)} {tipo}s carregados.")
        return dados

    except Exception as e:
        print(f"❌ Erro crítico no download: {e}")
        return {}

# --- 3. BAIXANDO AS BASES ---
print("Iniciando downloads dos Benchmarks...")

# URLs Oficiais do PassMark
cpu_db = baixar_tabela_benchmark_rapido("https://www.cpubenchmark.net/high_end_cpus.html", "CPU")
# Se a CPU não estiver na lista High End, pegamos a Mid Range também
cpu_db_mid = baixar_tabela_benchmark_rapido("https://www.cpubenchmark.net/mid_range_cpus.html", "CPU_MID")
cpu_db.update(cpu_db_mid)

gpu_db = baixar_tabela_benchmark_rapido("https://www.videocardbenchmark.net/high_end_gpus.html", "GPU")
gpu_db_mid = baixar_tabela_benchmark_rapido("https://www.videocardbenchmark.net/mid_range_gpus.html", "GPU_MID")
gpu_db.update(gpu_db_mid)

# --- 4. LENDO E PREPARANDO A PLANILHA ---
print("\n📖 Lendo seus notebooks da planilha...")
rows = worksheet.get_all_values()
headers = rows[0]
data = rows[1:]

# Mapeia colunas
try:
    idx_cpu = headers.index("CPU")
    idx_gpu = headers.index("GPU")
    idx_preco = headers.index("Preço")
    
    # Cria colunas de score se não existirem
    if "Score CPU" not in headers:
        print("🔧 Criando colunas de Score...")
        headers.extend(["Score CPU", "Score GPU", "Custo-Benefício"])
        worksheet.update('1:1', [headers])
        # Recalcula índices
        idx_score_cpu = len(headers) - 3
        idx_score_gpu = len(headers) - 2
        idx_cb = len(headers) - 1
    else:
        idx_score_cpu = headers.index("Score CPU")
        idx_score_gpu = headers.index("Score GPU")
        idx_cb = headers.index("Custo-Benefício")

except ValueError:
    print("❌ Erro: Verifique se as colunas CPU, GPU e Preço existem na aba 'Dados'.")
    raise

# --- 5. CRUZAMENTO DE DADOS (FUZZY MATCH) ---
print("\n🔍 Calculando pontuações e custo-benefício...")

novos_dados = []
lista_cpus_passmark = list(cpu_db.keys())
lista_gpus_passmark = list(gpu_db.keys())

contador = 0
total = len(data)

for row in data:
    contador += 1
    # Garante tamanho da linha
    while len(row) < len(headers):
        row.append("")
        
    notebook_cpu = row[idx_cpu]
    notebook_gpu = row[idx_gpu]
    
    # Trata preço (R$ 3.500,00 -> 3500.0)
    preco_raw = row[idx_preco]
    try:
        if isinstance(preco_raw, str):
            # Remove R$, ponto de milhar e troca vírgula por ponto
            p = preco_raw.replace("R$", "").replace(".", "").replace(",", ".").strip()
            preco = float(p) if p else 1.0
        else:
            preco = float(preco_raw)
    except:
        preco = 1.0

    # 1. SCORE CPU
    score_cpu = 0
    if notebook_cpu and notebook_cpu != "N/A":
        # Remove marcas para facilitar o match
        busca = notebook_cpu.replace("Intel", "").replace("AMD", "").replace("Core", "").strip()
        # Procura o melhor match
        match, nota = process.extractOne(busca, lista_cpus_passmark)
        if nota > 80:
            score_cpu = cpu_db[match]
        # else: print(f"  [CPU Baixa Confiança] {notebook_cpu} -> {match} ({nota}%)")

    # 2. SCORE GPU
    score_gpu = 0
    if notebook_gpu and notebook_gpu != "N/A":
        busca = notebook_gpu.replace("NVIDIA", "").replace("GeForce", "").replace("Dedicada", "").strip()
        # Truque: Tentar forçar 'Laptop GPU' pois o PassMark separa desktop de mobile
        match_info = process.extractOne(busca + " Laptop GPU", lista_gpus_passmark)
        
        # Se não achar bom match com "Laptop GPU", tenta normal
        if match_info[1] < 80:
             match_info = process.extractOne(busca, lista_gpus_passmark)
             
        if match_info[1] > 75:
            score_gpu = gpu_db[match_info[0]]

    # 3. CÁLCULO FINAL (Sua Fórmula)
    # (CPU * 0.4 + GPU * 0.6) / Preço
    if preco > 100:
        performance_mista = (score_cpu * 0.4) + (score_gpu * 0.6)
        # Multiplico por 1000 apenas para ficar um número mais legível (Ex: 8.5 em vez de 0.0085)
        cb = round((performance_mista / preco) * 1000, 2)
    else:
        cb = 0

    # Atualiza a linha
    row[idx_score_cpu] = score_cpu
    row[idx_score_gpu] = score_gpu
    row[idx_cb] = cb
    
    novos_dados.append(row)
    if contador % 10 == 0:
        print(f"Processado {contador}/{total} notebooks...")

# --- 6. SALVAR ---
print("\n💾 Salvando dados atualizados no Google Sheets...")
# Atualiza da linha 2 até o fim (preserva cabeçalho)
worksheet.update(range_name='A2', values=novos_dados)
print("✅ Concluído! Pode abrir a planilha e ordenar pela coluna 'Custo-Benefício'.")