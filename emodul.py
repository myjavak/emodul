import requests
import json
import time
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import streamlit_authenticator as stauth 

# --- KONFIGURÁCIA API (Čítanie z Streamlit Secrets) ---
try:
    BASE_URL = st.secrets["API_CONFIG"]["BASE_URL"]
    USER_EMAIL = st.secrets["API_CONFIG"]["EMAIL"]
    USER_PASSWORD = st.secrets["API_CONFIG"]["PASSWORD"]
    USER_ID = st.secrets["API_CONFIG"]["USER_ID"]
    MODULE_UDID = st.secrets["API_CONFIG"]["MODULE_UDID"]
    MENU_TYPE = "MU"
except KeyError as e:
    st.error(f"❌ Chyba konfigurácie Secrets: Chýba kľúč {e}. Skontrolujte nastavenie v Streamlit Cloud.")
    st.stop() 

REGULATOR_IDS = {
    "zóna_1": 4615, 
    "zóna_2": 4616,
    "zóna_3": 4617,
}

# --- KONFIGURÁCIA LOGOVANIA ---
LOG_FILE = "teplota_log.csv"
DAYS_TO_SHOW = 3 

# --- KONFIGURÁCIA AUTENTIFIKÁCIE (Formát pre V0.1.5) ---
NAMES = ['Admin User']
USERNAMES = ['admin']
# Heslo: admin123 (Použitý haš)
HASHED_PASSWORDS = ['kai8Jaem'] 

# --- CACHED FUNKCIE (API VOLANIA) ---

@st.cache_data(ttl=3600) 
def login(email, password):
    url = f"{BASE_URL}/authentication"
    payload = {"username": email, "password": password}
    headers = {"Content-Type": "application/json"}
    
    with st.spinner("🔑 Prihlasujem sa k eModul API..."):
        r = requests.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
        if not token:
            raise Exception(f"Nenašiel som token v odpovedi.")
        return token

@st.cache_data(ttl=65) 
def get_module_status(user_id, module_udid, token):
    url = f"{BASE_URL}/users/{user_id}/modules/{module_udid}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

def set_temperature(user_id, module_udid, token, reg_id, temp_c):
    url = f"{BASE_URL}/users/{user_id}/modules/{module_udid}/menu/{MENU_TYPE}/ido/{reg_id}"
    payload = {"value": int(round(temp_c * 10))} 
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return True

# --- FUNKCIE PRE LOGOVANIE A ŠTATISTIKY ---

def log_temperature(status_data, log_file):
    data_list = status_data.get("tiles", [])
    current_time = datetime.now()
    log_entry = {'timestamp': current_time}
    for zone_name, reg_id in REGULATOR_IDS.items():
        target_item = next((item for item in data_list if item.get("id") == reg_id), None)
        if target_item:
            raw_current = target_item.get("params", {}).get("widget2", {}).get("value")
            log_entry[zone_name] = raw_current / 10.0 if isinstance(raw_current, (int, float)) else None
    new_df = pd.DataFrame([log_entry])
    new_df = new_df.set_index('timestamp')
    if os.path.exists(log_file):
        try:
            df_existing = pd.read_csv(log_file, index_col='timestamp', parse_dates=True)
            df_combined = pd.concat([df_existing, new_df])
            df_combined = df_combined[~df_combined.index.duplicated(keep='last')] 
        except Exception:
            df_combined = new_df
    else:
        df_combined = new_df
    time_limit = current_time - timedelta(days=DAYS_TO_SHOW)
    df_combined = df_combined[df_combined.index >= time_limit]
    df_combined.to_csv(log_file)
    return df_combined

def show_statistics_page(log_file, days_to_show):
    st.title("📈 Historické Štatistiky Teploty")
    st.markdown(f"Zobrazenie dát za posledných **{days_to_show} dní**.")
    if not os.path.exists(log_file):
        st.warning("Zatiaľ neboli zaznamenané žiadne historické dáta. Záznam sa spustí pri najbližšej aktualizácii.")
        return
    try:
        df = pd.read_csv(log_file, index_col='timestamp', parse_dates=True)
        time_limit = datetime.now() - timedelta(days=days_to_show)
        df_filtered = df[df.index >= time_limit]
        if df_filtered.empty:
            st.warning("V logu nie sú žiadne záznamy pre dané časové obdobie.")
            return
        st.line_chart(df_filtered)
        st.subheader("Detail Logovacích Dát")
        st.dataframe(df_filtered)
    except Exception as e:
        st.error(f"Chyba pri načítaní a zobrazení historických dát: {e}")

# --- INICIALIZÁCIA AUTENTIFIKÁTORA (Formát pre V0.1.5) ---

authenticator = stauth.Authenticate(
    NAMES,
    USERNAMES,
    HASHED_PASSWORDS,
    'termostat_cookie',
    'abcdef', 
)

# ZOBRAZÍ LOGIN FORMULÁR A VRÁTI STAV (Formát pre V0.1.5)
name, authentication_status, username = authenticator.login('Login Form', 'main') 


# --- HLAVNÝ BEH APLIKÁCIE ---

# 1. Ak je užívateľ ÚSPEŠNE PRIHLÁSENÝ
if authentication_status: 
    
    # --- BOČNÉ MENU A LOGOUT ---
    authenticator.logout('Odhlásiť sa', location='sidebar')
    
    if 'page' not in st.session_state:
        st.session_state.page = 'Control'

    st.sidebar.title(f"Vitaj, {name}!")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("Ovládací Panel (Aktuálny Stav)"):
        st.session_state.page = 'Control'
    if st.sidebar.button("Historické Štatistiky"):
        st.session_state.page = 'Statistics'
    
    st.sidebar.markdown("---")

    # --- KONTROLNÝ/ŠTATISTICKÝ KÓD ---
    try:
        # 1. Prihlásenie a získanie tokenu
        token = login(USER_EMAIL, USER_PASSWORD)
        
        # 2. Získanie Aktuálneho Stavu
        status_data = get_module_status(USER_ID, MODULE_UDID, token)

        # 3. Logovanie dát 
        log_df = log_temperature(status_data, LOG_FILE)
        
        
        if st.session_state.page == 'Control':
            # --- KONTROLNÁ STRÁNKA ---
            st.title("🌡️ eModul Termostat Ovládanie")
            st.markdown("---")
            
            st.header("1. Aktuálny Stav Zón")
            data_list = status_data.get("tiles", [])
            cols = st.columns(3)
            
            i = 0
            for zone_name, reg_id in REGULATOR_IDS.items():
                col = cols[i % 3]
                target_item = next((item for item in data_list if item.get("id") == reg_id), None)
                
                if target_item:
                    params = target_item.get("params", {})
                    raw_current = params.get("widget2", {}).get("value")
                    raw_setpoint = params.get("widget1", {}).get("value")
                    raw_status_id = params.get("statusId") 
                    
                    aktualna_teplota = f"{raw_current/10.0:.1f}°C" if isinstance(raw_current, (int, float)) else "N/A"
                    nastavena_teplota = f"{raw_setpoint/10.0:.1f}°C" if isinstance(raw_setpoint, (int, float)) else "N/A"
                    
                    status_emoji = "🔥" if raw_status_id == 0 else "❄️"
                    status_text = "KÚRI" if raw_status_id == 0 else "VYPNUTÉ"
                    
                    with col:
                        st.subheader(f"{status_emoji} {zone_name.upper()}")
                        st.metric(label="Aktuálna Teplota", value=aktualna_teplota)
                        st.metric(label="Nastavená Cieľová", value=nastavena_teplota)
                        st.caption(f"Status ID: {raw_status_id} ({status_text})")
                i += 1
            
            st.markdown("---")

            # --- SEKCIA PRE OKAMŽITÉ NASTAVENIE ---
            st.header("2. Okamžité Nastavenie Teploty")
            col_zone, col_temp = st.columns(2)
            
            selected_zone = col_zone.selectbox(
                "Vyberte zónu na zmenu:", 
                options=list(REGULATOR_IDS.keys())
            )
            
            current_setpoint = next((raw_setpoint/10.0 for zn, rid in REGULATOR_IDS.items() if zn == selected_zone for item in data_list if item.get("id") == rid and 'widget1' in item.get('params', {})), 20.0)

            target_temp = col_temp.number_input(
                "Nová cieľová teplota (°C):", 
                min_value=5.0, 
                max_value=30.0, 
                value=current_setpoint, 
                step=0.5,
                key='temp_input'
            )
            
            reg_id_to_set = REGULATOR_IDS[selected_zone]
            
            if st.button(f"🚀 Nastaviť {selected_zone.upper()} na {target_temp}°C"):
                
                try:
                    set_temperature(USER_ID, MODULE_UDID, token, reg_id_to_set, target_temp)
                    
                    st.success(f"Príkaz na nastavenie {selected_zone.upper()} na {target_temp}°C bol úspešne odoslaný.")
                    st.info("⚠️ Zmena cieľovej teploty sa v zobrazenom stave prejaví až **po cca 60 sekundách** (API oneskorenie).")
                    
                    get_module_status.clear()
                    
                except requests.exceptions.HTTPError as e:
                    st.error(f"❌ Chyba pri odosielaní príkazu: HTTP {e.response.status_code}. Skontrolujte logy.")
                except Exception as e:
                    st.error(f"❌ Vyskytla sa chyba: {e}")

        elif st.session_state.page == 'Statistics':
            # --- ŠTATISTICKÁ STRÁNKA ---
            show_statistics_page(LOG_FILE, DAYS_TO_SHOW)

    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Chyba pri pripojení k API (HTTP {e.response.status_code}). Skontrolujte prihlasovacie údaje alebo API stav.")
    except Exception as e:
        st.error(f"❌ Nastala kritická chyba aplikácie: {e}")

# 2. Ak NIE JE prihlásený, zobrazíme chybu
elif authentication_status is False:
    st.error('Používateľské meno/heslo je nesprávne.')
elif authentication_status is None:
    st.warning('Prosím, zadajte svoje prihlasovacie údaje na prístup.')

