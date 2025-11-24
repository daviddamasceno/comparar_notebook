import gspread
from google.auth import default
from google.colab import auth
import requests
from bs4 import BeautifulSoup
import time

# --- 1. AUTENTICAÇÃO ---
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

# Localiza a coluna de Link (geralmente a G)
try:
    idx_link = headers.index("Link")
except ValueError:
    raise Exception("❌ Coluna 'Link' não encontrada na planilha.")

# --- 2. FUNÇÃO DE EXTRAÇÃO (Lógica Validada) ---
def extrair_detalhes_ram_final(url):
    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    detalhes = {
        "geracao": "N/A",
        "soldada": "N/A",
        "slots": "0",
        "maximo": "N/A"
    }

    try:
        response = requests.get(url, headers=headers_browser, timeout=15)
        if response.status_code != 200: return detalhes
        
        soup = BeautifulSoup(response.text, 'html.parser')
        div_ram = soup.select_one("div.spec-row.ram")
        
        if not div_ram: return detalhes

        # A. GERAÇÃO
        try:
            txt = div_ram.select_one(".spec_ram_installed_capacity_and_type").get_text()
            if "DDR5" in txt: detalhes["geracao"] = "DDR5"
            elif "DDR4" in txt: detalhes["geracao"] = "DDR4"
            elif "LPDDR" in txt: detalhes["geracao"] = txt.split(" ")[1] # Pega LPDDRx
            else: detalhes["geracao"] = txt
        except: pass

        # B. MEMÓRIA MÁXIMA
        try:
            txt = div_ram.select_one(".spec_ram_max_capacity").get_text()
            # Limpeza para deixar apenas "64 GB" ou "32 GB"
            detalhes["maximo"] = txt.lower().replace("máximo de", "").replace("máximo", "").strip()
        except: pass

        # C. RAM SOLDADA (Verifica classes de indisponibilidade)
        try:
            li_soldada = div_ram.select_one(".spec_ram_onboard")
            if li_soldada:
                classes = li_soldada.get("class", [])
                texto = li_soldada.get_text().lower()
                
                if "not-available" in classes or "não possui" in texto:
                    detalhes["soldada"] = "Não possui"
                else:
                    detalhes["soldada"] = "Sim"
        except: pass

        # D. SLOTS (Conta apenas os ativos)
        try:
            lista_slots = div_ram.select("li[class^='spec_ram_slot_']")
            slots_reais = 0
            for slot in lista_slots:
                classes = slot.get("class", [])
                texto = slot.get_text().lower()
                # Só conta se NÃO estiver indisponível
                if "not-available" not in classes and "não possui" not in texto:
                    slots_reais += 1
            
            detalhes["slots"] = str(slots_reais)
        except: pass

    except Exception as e:
        print(f"Erro leve: {e}")
    
    return detalhes

# --- 3. LOOP DE PROCESSAMENTO ---
print(f"Iniciando extração de RAM para sobrescrever colunas M, N, O, P...")

novos_dados = []
# Definição Fixa dos Cabeçalhos para M, N, O, P
cabecalhos_ram = ["Geração DDR", "RAM Soldada", "Slots Ativos", "RAM Máxima"]

for i, row in enumerate(data):
    link = row[idx_link]
    
    if link:
        info = extrair_detalhes_ram_final(link)
        print(f"[{i+1}/{len(data)}] {info['geracao']} | Soldada: {info['soldada']} | Slots: {info['slots']}")
        linha = [info["geracao"], info["soldada"], info["slots"], info["maximo"]]
    else:
        linha = ["N/A", "N/A", "N/A", "N/A"]
        
    novos_dados.append(linha)
    time.sleep(0.5) # Delay para não sobrecarregar o servidor

# --- 4. SALVANDO NAS COLUNAS M, N, O, P ---
print("\n💾 Sobrescrevendo colunas M:P na planilha...")

# 1. Atualiza o Cabeçalho (Linha 1, Colunas M a P)
worksheet.update(range_name="M1:P1", values=[cabecalhos_ram])

# 2. Atualiza os Dados (Linha 2 em diante, Colunas M a P)
# O range final é P + número de linhas
range_dados = f"M2:P{len(novos_dados) + 1}"
worksheet.update(range_name=range_dados, values=novos_dados)

print("✅ Colunas M, N, O e P atualizadas com sucesso!")