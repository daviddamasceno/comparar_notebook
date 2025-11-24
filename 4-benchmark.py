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

try:
    sh = gc.open('Notebooks_Scraper')
    worksheet = sh.worksheet('Dados')
except Exception as e:
    print(f"❌ Erro ao abrir planilha: {e}")
    raise e

# --- 2. BAIXAR BENCHMARKS (MÉTODO RÁPIDO) ---
def baixar_tabela_benchmark_rapido(url, tipo="CPU"):
    print(f"📥 Baixando dados de {tipo}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        dados = {}
        rows = soup.select("ul.chartlist li")
        for row in rows:
            try:
                nome = row.select_one("span.prdname").get_text(strip=True)
                score = int(row.select_one("span.count").get_text(strip=True).replace(",", ""))
                # Limpeza para facilitar o match
                nome_limpo = nome.replace("Intel", "").replace("AMD", "").replace("NVIDIA", "").strip()
                dados[nome_limpo] = score
            except: continue
        print(f"✅ {len(dados)} {tipo}s carregados.")
        return dados
    except: return {}

# Executa Downloads
cpu_db = baixar_tabela_benchmark_rapido("https://www.cpubenchmark.net/high_end_cpus.html", "CPU")
cpu_db.update(baixar_tabela_benchmark_rapido("https://www.cpubenchmark.net/mid_range_cpus.html", "CPU_MID"))

gpu_db = baixar_tabela_benchmark_rapido("https://www.videocardbenchmark.net/high_end_gpus.html", "GPU")
gpu_db.update(baixar_tabela_benchmark_rapido("https://www.videocardbenchmark.net/mid_range_gpus.html", "GPU_MID"))

lista_cpus = list(cpu_db.keys())
lista_gpus = list(gpu_db.keys())

# --- 3. PROCESSAMENTO DA PLANILHA ---
print("\n📖 Lendo planilha e reestruturando colunas...")
rows = worksheet.get_all_values()
original_headers = rows[0]
data = rows[1:]

# Identifica as colunas base (Modelo, Preço... até Link)
colunas_fixas = ["Modelo", "Preço", "Cupom", "CPU", "GPU", "RAM", "Link"]

# Define os NOVOS cabeçalhos na ordem pedida
novos_cabecalhos = colunas_fixas + [
    "Score CPU", 
    "CB CPU",        
    "Score GPU", 
    "CB GPU",        
    "Custo-Benefício Total"
]

# Mapeia índices das colunas originais para leitura
try:
    idx_cpu = original_headers.index("CPU")
    idx_gpu = original_headers.index("GPU")
    idx_preco = original_headers.index("Preço")
    idx_modelo = original_headers.index("Modelo")
    idx_cupom = original_headers.index("Cupom")
    idx_ram = original_headers.index("RAM")
    idx_link = original_headers.index("Link")
except ValueError:
    print("❌ Erro: Faltam colunas básicas (CPU, GPU, Preço, Link, etc). Rode o scraper novamente.")
    raise

print("\n🔍 Calculando novas métricas...")
dados_finais = []
dados_finais.append(novos_cabecalhos)

count = 0
for row in data:
    count += 1
    
    try:
        modelo = row[idx_modelo]
        preco_raw = row[idx_preco]
        cupom = row[idx_cupom] if len(row) > idx_cupom else ""
        cpu_txt = row[idx_cpu]
        gpu_txt = row[idx_gpu]
        ram = row[idx_ram]
        link = row[idx_link]
    except: continue 

    # 2. Tratamento e VALIDAÇÃO de Preço
    preco = 0.0
    preco_valido = False
    
    try:
        if isinstance(preco_raw, str):
            # Remove R$, pontos e troca vírgula por ponto
            p = preco_raw.replace("R$", "").replace(".", "").replace(",", ".").strip()
            # Remove qualquer caractere não numérico que tenha sobrado
            p = ''.join(c for c in p if c.isdigit() or c == '.')
            preco = float(p) if p else 0.0
        else: 
            preco = float(preco_raw)
    except: 
        preco = 0.0
    
    # --- A CORREÇÃO PRINCIPAL ---
    # Se o preço for menor que 100 (ex: 0, 1, ou muito baixo), consideramos inválido para cálculo
    if preco > 100:
        preco_valido = True
    else:
        preco_valido = False

    # 3. Match CPU
    score_cpu = 0
    if cpu_txt and cpu_txt != "N/A":
        busca = cpu_txt.replace("Intel", "").replace("AMD", "").replace("Core", "").strip()
        match, nota = process.extractOne(busca, lista_cpus)
        if nota > 80: score_cpu = cpu_db[match]

    # 4. Match GPU
    score_gpu = 0
    if gpu_txt and gpu_txt != "N/A":
        busca = gpu_txt.replace("NVIDIA", "").replace("GeForce", "").replace("Dedicada", "").strip()
        match_info = process.extractOne(busca + " Laptop GPU", lista_gpus)
        if match_info[1] < 80: match_info = process.extractOne(busca, lista_gpus)
        if match_info[1] > 75: score_gpu = gpu_db[match_info[0]]

    # 5. CÁLCULOS (Só executa se o preço for válido)
    if preco_valido:
        # CB CPU (Individual)
        cb_cpu = round((score_cpu / preco) * 1000, 2)
        
        # CB GPU (Individual)
        cb_gpu = round((score_gpu / preco) * 1000, 2)
        
        # CB Total (Ponderado 40/60)
        pontos_misto = (score_cpu * 0.4) + (score_gpu * 0.6)
        cb_total = round((pontos_misto / preco) * 1000, 2)
    else:
        # Se o preço for inválido (ex: 1), zera tudo para não poluir o ranking
        cb_cpu = 0.0
        cb_gpu = 0.0
        cb_total = 0.0

    # 6. Monta a nova linha
    nova_linha = [
        modelo, 
        preco if preco_valido else 0, # Salva 0 se for inválido para ficar claro visualmente
        cupom, 
        cpu_txt, 
        gpu_txt, 
        ram, 
        link,
        score_cpu, 
        cb_cpu,     
        score_gpu,  
        cb_gpu,     
        cb_total    
    ]
    
    dados_finais.append(nova_linha)
    if count % 10 == 0: print(f"Processado {count}...")

# --- 4. SALVAR ---
print("\n💾 Salvando na planilha...")
# ATENÇÃO: Isso vai apagar as colunas de RAM detalhada se você rodar isso depois do script de RAM
# Recomendo rodar este script PRIMEIRO e depois o de RAM, ou ajustar o intervalo de escrita.
# Vou limpar e escrever do zero para garantir a integridade dos cálculos.
worksheet.clear() 
worksheet.update(range_name='A1', values=dados_finais)

worksheet.format("B:B", {"numberFormat": {"type": "CURRENCY", "pattern": "R$ #,##0.00"}})

print("✅ Planilha atualizada! Notebooks com preço simbólico (1.00) agora têm CB zerado.")