import gspread
from google.auth import default
from google.colab import auth
import requests
from bs4 import BeautifulSoup
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

# --- 2. FUNÇÃO DE EXTRAÇÃO (LÓGICA ROBUSTA) ---
def extrair_detalhes_ram(url):
    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Valores padrão
    detalhes = {
        "geracao": "N/A",
        "soldada": "Check Manual",
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
            elif "LPDDR" in txt: detalhes["geracao"] = txt.split(" ")[1]
            else: detalhes["geracao"] = txt
        except: pass

        # B. MÁXIMO
        try:
            txt = div_ram.select_one(".spec_ram_max_capacity").get_text()
            detalhes["maximo"] = txt.lower().replace("máximo de", "").replace("máximo", "").strip()
        except: pass

        # C. SOLDADA (Validação de classe 'not-available')
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

        # D. SLOTS (Validação um a um)
        try:
            lista_slots = div_ram.select("li[class^='spec_ram_slot_']")
            slots_reais = 0
            for slot in lista_slots:
                classes = slot.get("class", [])
                texto = slot.get_text().lower()
                # Só conta se estiver ativo
                if "not-available" not in classes and "não possui" not in texto:
                    slots_reais += 1
            detalhes["slots"] = str(slots_reais)
        except: pass

    except: pass
    
    return detalhes

# --- 3. PREPARAÇÃO DA ESTRUTURA DE DADOS ---
print("\n📖 Lendo planilha atual...")
rows = worksheet.get_all_values()
headers = rows[0]
data = rows[1:]

# Localiza Link
try:
    idx_link = headers.index("Link")
except:
    raise Exception("❌ Coluna 'Link' não encontrada.")

# Definição das novas colunas
colunas_ram = ["Geração DDR", "RAM Soldada", "Slots Ativos", "RAM Máxima"]

# Verifica se as colunas JÁ existem para não duplicar
indices_ram = {}
novos_headers = headers.copy()

# Se não existirem, cria no final. Se existirem, pega o índice.
for col in colunas_ram:
    if col in headers:
        indices_ram[col] = headers.index(col)
    else:
        novos_headers.append(col)
        indices_ram[col] = len(novos_headers) - 1

print(f"Estrutura definida. Total de colunas: {len(novos_headers)}")

# --- 4. LOOP DE PROCESSAMENTO E RECONSTRUÇÃO ---
print("\n🔍 Extraindo dados de RAM (Isso garante a integridade da planilha)...")

dados_finais = [novos_headers] # Começa com o cabeçalho
total = len(data)

for i, row in enumerate(data):
    # Garante que a linha tenha tamanho suficiente para as novas colunas
    while len(row) < len(novos_headers):
        row.append("")
    
    link = row[idx_link]
    
    if link:
        info = extrair_detalhes_ram(link)
        print(f"[{i+1}/{total}] {info['geracao']} | Soldada: {info['soldada']} | Slots: {info['slots']}")
        
        # Atualiza os índices corretos (seja coluna nova ou existente)
        row[indices_ram["Geração DDR"]] = info["geracao"]
        row[indices_ram["RAM Soldada"]] = info["soldada"]
        row[indices_ram["Slots Ativos"]] = info["slots"]
        row[indices_ram["RAM Máxima"]] = info["maximo"]
    
    dados_finais.append(row)
    time.sleep(0.5)

# --- 5. SALVAR SEGURO (CLEAR + UPDATE) ---
print("\n💾 Salvando planilha completa...")
worksheet.clear()
worksheet.update(range_name='A1', values=dados_finais)

# Refaz a formatação de preço (caso tenha se perdido no clear)
try:
    # Assume que Preço é coluna B, mas podemos achar dinamicamente
    idx_p = novos_headers.index("Preço")
    # Converte indice 1 (B) para letra
    letra_p = chr(65 + idx_p) 
    worksheet.format(f"{letra_p}:{letra_p}", {"numberFormat": {"type": "CURRENCY", "pattern": "R$ #,##0.00"}})
except: pass

print("✅ Planilha atualizada! Dados de RAM inseridos/atualizados.")