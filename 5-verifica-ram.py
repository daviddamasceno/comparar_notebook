import gspread
from google.auth import default
from google.colab import auth
import requests
from bs4 import BeautifulSoup
import time
import re

# --- 1. AUTENTICAÇÃO E LEITURA ---
print("Autenticando...")
auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

sh = gc.open('Notebooks_Scraper')
worksheet = sh.worksheet('Dados')

# Lê todos os dados para pegar os links
rows = worksheet.get_all_values()
headers = rows[0]
data = rows[1:]

# Encontra a coluna de Link
try:
    idx_link = headers.index("Link")
except ValueError:
    raise Exception("❌ Coluna 'Link' não encontrada. Rode o scraper principal primeiro.")

# --- 2. FUNÇÃO DE EXTRAÇÃO DE RAM ---
def extrair_detalhes_ram(url):
    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    detalhes = {
        "geracao": "N/A",
        "soldada": "N/A",
        "slots": "N/A",
        "maximo": "N/A"
    }

    try:
        response = requests.get(url, headers=headers_browser, timeout=15)
        if response.status_code != 200: return detalhes
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Localiza o bloco de memória
        div_ram = soup.select_one("div.spec-row.ram")
        if not div_ram: return detalhes

        # A. GERAÇÃO (DDR4 / DDR5)
        # Procura em: <p class="spec_ram_installed_capacity_and_type">
        try:
            texto_tipo = div_ram.select_one(".spec_ram_installed_capacity_and_type").get_text()
            if "DDR5" in texto_tipo: detalhes["geracao"] = "DDR5"
            elif "DDR4" in texto_tipo: detalhes["geracao"] = "DDR4"
            elif "LPDDR5" in texto_tipo: detalhes["geracao"] = "LPDDR5"
            elif "LPDDR4" in texto_tipo: detalhes["geracao"] = "LPDDR4"
            else: detalhes["geracao"] = texto_tipo.replace("GB", "").strip()
        except: pass

        # B. MEMÓRIA MÁXIMA
        # Procura em: <p class="spec_ram_max_capacity">
        try:
            texto_max = div_ram.select_one(".spec_ram_max_capacity").get_text()
            # Limpa "Máximo de " e deixa só "32 GB" ou "64 GB"
            detalhes["maximo"] = texto_max.lower().replace("máximo de", "").replace("máximo", "").strip()
        except: pass

        # C. É SOLDADA?
        # Procura em: <li class="spec_ram_onboard">
        try:
            texto_soldada = div_ram.select_one(".spec_ram_onboard").get_text()
            if "não possui" in texto_soldada.lower():
                detalhes["soldada"] = "Não"
            else:
                detalhes["soldada"] = "Sim"
        except: pass

        # D. QUANTIDADE DE SLOTS
        # Conta quantos <li> existem com classes que começam com 'spec_ram_slot_'
        # Exemplo: spec_ram_slot_1, spec_ram_slot_2
        try:
            slots_encontrados = div_ram.select("li[class^='spec_ram_slot_']")
            qtd_slots = len(slots_encontrados)
            
            # Verifica se algum slot diz "Não possui" (alguns modelos mostram o slot na lista mas dizem que não tem)
            # Mas geralmente nesse site, se aparece na lista, é um slot físico (mesmo que vazio).
            # Vamos assumir a contagem de LIs como slots físicos disponíveis na placa.
            detalhes["slots"] = str(qtd_slots)
        except: pass

    except Exception as e:
        print(f"Erro na extração: {e}")
    
    return detalhes

# --- 3. LOOP DE ATUALIZAÇÃO ---
print(f"Iniciando detalhamento de RAM para {len(data)} notebooks...")
print("Isso vai levar alguns segundos por notebook...")

novas_colunas_dados = []

# Cabeçalhos das novas colunas
novos_headers = ["Geração DDR", "RAM Soldada?", "Qtd Slots", "RAM Máxima"]

for i, row in enumerate(data):
    link = row[idx_link]
    
    if link:
        info = extrair_detalhes_ram(link)
        linha_dados = [info["geracao"], info["soldada"], info["slots"], info["maximo"]]
        print(f"[{i+1}/{len(data)}] {info['geracao']} | Max: {info['maximo']} | Slots: {info['slots']}")
    else:
        linha_dados = ["N/A", "N/A", "N/A", "N/A"]
        
    novas_colunas_dados.append(linha_dados)
    # Pausa suave para não ser bloqueado
    time.sleep(1)

# --- 4. SALVANDO NO GOOGLE SHEETS ---
print("\n💾 Salvando novas colunas na planilha...")

# Determina onde começar a escrever (Coluna depois da última existente)
# Vamos supor que você tem 12 colunas atualmente (A até L). A próxima é M (13).
coluna_inicio_num = len(headers) + 1 

# Função auxiliar para converter número em letra de coluna (13 -> M, 27 -> AA)
def col_num_to_letter(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

letra_inicio = col_num_to_letter(coluna_inicio_num)
letra_fim = col_num_to_letter(coluna_inicio_num + 3)

# Atualiza Cabeçalhos
range_header = f"{letra_inicio}1:{letra_fim}1"
worksheet.update(range_name=range_header, values=[novos_headers])

# Atualiza Dados
range_dados = f"{letra_inicio}2:{letra_fim}{len(data)+1}"
worksheet.update(range_name=range_dados, values=novas_colunas_dados)

print("✅ Detalhamento de RAM concluído com sucesso!")