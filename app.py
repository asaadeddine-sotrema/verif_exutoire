"""
Application de Vérification des Exutoires (Dupille, Picheta, SUEZ, Valène).
Permet le rapprochement entre les pesées Terrain (SOTREMA) et les pesées Facture (Exutoires).

Modules :
- Authentication (Login/Logout/Cookies)
- Database (PostgreSQL via SQLAlchemy)
- Data Processing (Specific logic per provider)
- Dashboard (Streamlit UI with Filters & KPIs)

Auteur : Amine
Dernière M.A.J : Février 2026
"""

import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import datetime
import bcrypt
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.dialects.postgresql import insert
import json
from dotenv import load_dotenv
import os
import matplotlib.pyplot as plt
import logging
import extra_streamlit_components as stx
from logging_config import setup_logging
# IMPORTS DES MODULES ADITIONNELS
try:
    from modules.verif_heures_ui import show_verif_heures_ui
except Exception as e:
    import logging
    import streamlit as st
    import_error_msg = str(e)
    logging.error(f"Erreur d'importation de verif_heures_ui : {import_error_msg}")
    def show_verif_heures_ui(engine=None, mode=None):
        st.error(f"❌ Le module 'Vérification Heures' n'a pas pu être chargé. Erreur : {import_error_msg}")

try:
    from modules.verif_ecorec_ui import show_verif_ecorec_ui
except Exception as e:
    import logging
    import streamlit as st
    logging.error(f"Erreur d'importation de verif_ecorec_ui : {e}")
    def show_verif_ecorec_ui():
        st.error(f"❌ Le module 'Vérification Ecorec' n'a pas pu être chargé. Erreur : {e}")

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================


# Initialisation du logging (Mise en cache pour éviter le spam "Logging initialisé" à chaque action)
class UserContextFilter(logging.Filter):
    def filter(self, record):
        try:
            # On tente de récupérer le user dans la session
            user = st.session_state.get("username", "System")
        except:
            user = "System"
        record.user_id = user
        return True

@st.cache_resource
def init_logger():
    setup_logging()
    root_logger = logging.getLogger()
    
    # Ajout du filtre de contexte (User ID)
    f = UserContextFilter()
    root_logger.addFilter(f)
    
    # Mise à jour du format pour inclure [User]
    new_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(user_id)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    for handler in root_logger.handlers:
        handler.setFormatter(new_formatter)
        
    return root_logger

logger = init_logger()


st.set_page_config(page_title="Verif Exutoires", page_icon="♻️", layout="wide")
load_dotenv(override=True)

TABLE_NAME = "verif_tonnage_historique"
COLS_SQL = [
    "Date", "Exutoire", "Client", "INT Client", "EXT Client", "Activité",
    "Num Ticket", "Num Bon", "Chauffeur", "Immatriculation",
    "EXT_Matiere", "Matiere_T",
    "Verif_Tonnes", "Verif_Matiere", "Verif_Exutoire", "Verif_Client",
    "Poids_Terrain", "Poids_Facture", "Ecart", "isActive", "Motif", "Dernier_Utilisateur"
]


# =============================================================================
# DATABASE CONNECTION
# =============================================================================
@st.cache_resource
def get_db_engine():
    try:
        from cryptography.fernet import Fernet
        from urllib.parse import quote_plus
        
        db_key = os.getenv('DB_KEY')
        db_pass_encrypted = os.getenv('DB_PASS')
        
        suite = Fernet(db_key.encode())
        db_pass_decrypted = suite.decrypt(db_pass_encrypted.encode()).decode()
        
        encoded_user = quote_plus(os.getenv('DB_USER'))
        encoded_pass = quote_plus(db_pass_decrypted)
        
        url = f"postgresql://{encoded_user}:{encoded_pass}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
        return create_engine(url)
    except Exception as e:
        logger.error(f"Erreur Connexion DB: {e}")
        st.error(f"Erreur Connexion DB: {e}")
        return None

def check_and_migrate_db(engine):
    """
    Vérifie et met à jour le schéma de la base de données.
    Ajoute les colonnes manquantes (isActive, Motif, Validation_*) si nécessaire.
    """
    try:
        with engine.connect() as conn:
            columns_to_add = {
                "isActive": "BOOLEAN DEFAULT TRUE",
                "Motif": "TEXT",
                "Dernier_Utilisateur": "TEXT",
                "Validation_Tonnes": "BOOLEAN DEFAULT FALSE",
                "Validation_Client": "BOOLEAN DEFAULT FALSE",
                "Validation_Matiere": "BOOLEAN DEFAULT FALSE",
                "Validation_Exutoire": "BOOLEAN DEFAULT FALSE",
                "Poids_Terrain_Original": "FLOAT",
                "Matiere_T_Original": "TEXT",
                "INT_Client_Original": "TEXT"
            }
            
            for col, col_type in columns_to_add.items():
                res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{TABLE_NAME}' AND column_name = '{col}'"))
                if res.rowcount == 0:
                    conn.execute(text(f'ALTER TABLE {TABLE_NAME} ADD COLUMN "{col}" {col_type}'))
                    conn.commit()
                    st.toast(f"✅ Migration : Colonne '{col}' ajoutée.")
    except Exception as e:
        logger.error(f"Erreur Migration : {e}")
        st.error(f"Erreur Migration : {e}")

from modules.verif_suez import convertir_date_suez

def login_screen():
    """
    Gère l'affichage du formulaire de connexion et l'authentification.
    Utilise bcrypt pour la vérification des mots de passe hachés.
    """
    st.markdown("""<style>.login-box { padding: 2rem; border-radius: 10px; border: 1px solid #ddd; }</style>""", unsafe_allow_html=True)
    
    with st.container():
        st.title("🔐 Connexion")
        user = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        
        env_users_json = os.getenv("APP_USERS")
        
        VALID_USERS = {}
        if env_users_json:
            try:
                VALID_USERS = json.loads(env_users_json)
            except json.JSONDecodeError:
                st.error("Erreur de configuration : APP_USERS n'est pas un JSON valide.")
        
        if st.button("Se connecter", type="primary"):
            try:
                if user in VALID_USERS and bcrypt.checkpw(password.encode('utf-8'), VALID_USERS[user].encode('utf-8')):
                    logger.info(f"Connexion réussie: {user}")
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = user
                    
                    expiry = datetime.datetime.now() + datetime.timedelta(hours=3)
                    cookie_manager.set("auth_user", user, expires_at=expiry)
                    
                    st.rerun()
                else:
                    logger.warning(f"Echec connexion pour utilisateur: {user}")
                    st.error("Identifiant ou mot de passe incorrect")
            except Exception as e:
                logger.error(f"Erreur Auth: {e}")
                st.error("Erreur d'authentification (vérifiez le format des mots de passe).")

def logout():
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    cookie_manager.delete("auth_user")
    st.rerun()




# =============================================================================
# UTILITAIRES DE DATA CLEANING
# =============================================================================

def nettoyer_texte(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

    """
    Convertit une entrée (str, float, int) en objet datetime.date de manière robuste.
    Gère les formats Excel (nombre de jours depuis 1900), ISO, et FR.
    """
def convertir_date_robuste(val):
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime.date)): 
        return val.date() if isinstance(val, pd.Timestamp) else val
    
    v_str = str(val).strip()
    
    # [USER REQUEST] STRICT FRENCH PARSING (DD/MM/YYYY)
    # On force dayfirst=True pour lire d'abord le JOUR, puis le MOIS.
    # Ex: 04/02/2026 -> 4 Février (et non 2 Avril)
    try:
        dt = pd.to_datetime(v_str, dayfirst=True, errors='coerce')
        if pd.notna(dt):
            return dt.date()
    except:
        pass

    # 2. Fallback manuel (Jour / Mois / Année)
    separators = ['/', '-', '.']
    for sep in separators:
        if sep in v_str:
            parts = v_str.split(sep)
            if len(parts) >= 3:
                try:
                    # STANDARD : d = parts[0], m = parts[1]
                    d = int(parts[0])
                    m = int(parts[1])
                    y = int(parts[2].split()[0]) # Gère '2026 00:00:00'
                    if y < 100: y += 2000
                    return datetime.date(y, m, d)
                except: continue
    
    return pd.NaT







def highlight_validated_rows(row, col_name):
    """Style les lignes validées avec une couleur verte."""
    if row.get(col_name) == True:
        return ['background-color: #d1e7dd; color: #0f5132'] * len(row)
    # Zebra fallback
    if isinstance(row.name, int) and row.name % 2 != 0:
         return ['background-color: rgba(128, 128, 128, 0.1)'] * len(row)
    return [''] * len(row)

def normaliser_matiere_dupille(val):
    v = str(val).upper().strip()
    if "DECHETS VERTS" in v: return "DECHETS VERTS"
    if "VEGETAUX" in v or "VÉGÉTAUX" in v: return "DECHETS VERTS"
    if "BOIS AB" in v: return "BOIS A"
    if "BOIS A" in v: return "BOIS A"
    if "BOIS B" in v: return "BOIS B"
    if "SOUCHES" in v: return "SOUCHES"
    if "GRAVATS" in v: return "GRAVATS"
    if "DIB" in v: return "DIB"
    return v # Default keep original if not matched or just unknown

def normaliser_matiere_picheta_valoseine(val):
    v = str(val).upper().strip()
    if "BOIS" in v: return "BOIS"
    if "GRAVAT" in v: return "GRAVATS"
    if "PLATRE" in v or "PLÂTRE" in v: return "PLATRE"
    if "VEGETAUX" in v or "VÉGÉTAUX" in v or "VERTS" in v or "DVE" in v: return "VEGETAUX"
    if "PAPIER" in v or "CARTON" in v: return "PAPIER/CARTON"
    if "FERRAILLE" in v: return "FERRAILLE"
    if "ENCOMBRANTS" in v or "DIB" in v: return "ENCOMBRANTS"
    return v

def normaliser_matiere_valene(valeur_origine):
    val = nettoyer_texte(valeur_origine)
    if any(x in val for x in ["DECHETS IND", "ORDURES MEN", "DIB", "O.M", "DECHETS INCINERABLES"]): return "ORDURES MENAGERES"
    if any(x in val for x in ["EMBALLAGES", "RECYCLABLES", "TRI SELECTIF"]): return "EMBALLAGES MENAGERS RECUPERES"
    if "VERRE" in val: return "VERRE"
    if "CARTON" in val: return "CARTON"
    if "BOIS" in val: return "BOIS"
    return val

def verify_aggregated_weights(df):
    """
    Checks if the sum of weights for an expanded group matches the invoice sum.
    If so, overrides Verif_Tonnes to OK.
    """

    if 'Expansion_Group' not in df.columns: 

        return df
    
    groups = df[df['Expansion_Group'].notna()]['Expansion_Group'].unique()

    
    for grp in groups:
        mask = df['Expansion_Group'] == grp
        sub = df[mask]
        
        sum_t = sub['Poids_Terrain'].sum()
        sum_f = sub['Poids_Facture'].sum()
        

        
        if abs(sum_t - sum_f) < 0.01:
            df.loc[mask, 'Verif_Tonnes'] = 'OK'
            
    return df

def verify_dupille_weights(df):
    """
    Vérifie la cohérence des tonnages pour les tickets agrégés (1 Bon Facture -> N Tickets Terrain).
    Compare la somme des 'Poids_Terrain' associés à un 'Num Bon' vs le 'Poids_Facture' unique.
    
    Args:
        df (pd.DataFrame): DataFrame contenant les colonnes 'Num Bon', 'Poids_Terrain', 'Poids_Facture'.
        
    Returns:
        pd.DataFrame: DataFrame avec la colonne 'Verif_Tonnes' mise à jour.
    """
    if 'Num Bon' not in df.columns: return df
    
    counts = df['Num Bon'].value_counts()
    multi_bons = counts[counts > 1].index.tolist()
    
    for bon in multi_bons:
        if not bon or str(bon) == 'nan': continue
        
        mask = df['Num Bon'] == bon
        sub = df[mask]
        
        sum_t = sub['Poids_Terrain'].sum()
        
        if 'Num Ticket_F' in sub.columns and sub['Num Ticket_F'].notna().any():
            sub_f_unique = sub.drop_duplicates(subset=['Num Ticket_F'])
            val_f = sub_f_unique['Poids_Facture'].sum()
        else:
            p_f_vals = sub['Poids_Facture'].loc[sub['Poids_Facture'] > 0]
            if p_f_vals.empty: continue
            val_f = p_f_vals.median()
        
        if abs(sum_t - val_f) < 0.01: 
            df.loc[mask, 'Verif_Tonnes'] = 'OK'
            
    return df

def normaliser_client_dupille(valeur_origine):
    if pd.isna(valeur_origine): return ""
    val = str(valeur_origine).strip().upper()
    
    prefixes_collecte = ["LU_", "MA_", "ME_", "JE_", "VE_", "SA_", "DI_"]
    if any(val.startswith(p) for p in prefixes_collecte): return "GPSEO"
    if val.startswith("AIDE RATTRAPAGE"): return "GPSEO"
    
    if "BATIMENT DE REMISAGE" in val: return "CTM MAGNANVILLE"
    
    return val

def expand_dupille_rows(df):
    """
    Gère les cas où un champ 'Num Ticket' contient une liste ou une plage (ex: '123-125').
    Divise la ligne en plusieurs rangées et répartit le poids équitablement.
    """
    new_rows = []
    dropped_indices = []
    
    for idx, row in df.iterrows():
        t1 = str(row.get('Num Ticket', '')).strip().upper()
        t2 = str(row.get('Num Ticket 2', '')).strip().upper()
        
        target_ticket = t2 if t1 in ['ST', 'NAN', '', 'NONE', '0', 'None', 'nan'] else t1
        
        clean_target = target_ticket.replace('-', ',').replace('/', ',').replace('+', ',')
        
        if ',' in clean_target:
             parts = [p.strip() for p in clean_target.split(',') if p.strip().isdigit()]
             if len(parts) > 1:
                 count = len(parts)
                 weight = row.get('Poids_Terrain', 0)
                 if pd.isna(weight): weight = 0
                 split_weight = weight / count
                 
                 for t_num in parts:
                    new_row = row.copy()
                    new_row['Num Ticket'] = str(t_num)
                    new_row['Poids_Terrain'] = split_weight
                    new_row['is_expanded'] = True
                    new_row['Expansion_Group'] = f"GRP_{idx}"
                    new_rows.append(new_row)
                 dropped_indices.append(idx)
                
    if dropped_indices:
        df_clean = df.drop(index=dropped_indices)
        if new_rows:
            df_expanded = pd.DataFrame(new_rows)
            return pd.concat([df_clean, df_expanded], ignore_index=True)
            
    return df

def clean_plate(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    return ''.join(c for c in txt if c.isalnum())

def clean_client_match(name):
    if pd.isna(name): return ""
    n = str(name).upper().strip()
    if "CLOSEAUX" in n: return "CLOSEAUX"
    if "VAUCOULEURS" in n: return "VAUCOULEURS"
    if "LIMAY" in n: return "LIMAY"
    n = n.replace('DECHETTERIE', '').replace('PICHETA', '').replace('MLV', '').replace('MLJ', '')
    return ''.join(c for c in n if c.isalnum())

def check_client_compatibility(row, col_int, col_ext):
    val_int = row.get(col_int, "")
    val_ext = row.get(col_ext, "")
    if pd.isna(val_int) or str(val_int).strip() == "": return True
    if pd.isna(val_ext) or str(val_ext).strip() == "": return True
    c_int = clean_client_match(val_int)
    c_ext = clean_client_match(val_ext)
    if not c_int or not c_ext: return True
    if c_int == c_ext: return True
    if c_int in c_ext or c_ext in c_int: return True
    return False

# =============================================================================
# LOGIQUE DE MATCHING & NORMALISATION
# =============================================================================

from modules.verif_suez import normalize_site_key, check_site_keys
# (normalize_site_key and check_site_keys moved to modules/verif_suez.py)

def resolve_col(df, col_base):
    """
    Tente de résoudre la valeur d'une colonne en cherchant d'abord dans la base (`col`),
    puis dans le Terrain (`col_T`), puis dans la Facture (`col_F`).
    """
    fallback = pd.Series([np.nan] * len(df), index=df.index)
    c_t = df.get(f"{col_base}_T", fallback)
    c_f = df.get(f"{col_base}_F", fallback)
    
    if col_base in df.columns:
        return df[col_base].fillna(c_t).fillna(c_f)
        
    return c_t.fillna(c_f)


# =============================================================================
# PERSISTANCE EN BASE DE DONNÉES
# =============================================================================

def save_to_db(df, engine):
    """
    Sauvegarde le DataFrame en base de données avec gestion des conflits (Upsert).
    
    Règles :
    - Clé unique : (Num Ticket, Exutoire, Num Bon)
    - Met à jour les données existantes sans dupliquer.
    - Supprime les anciens doublons SUEZ (basé sur Num Bon) avant insertion si nécessaire.
    """
    if df is None:
        st.warning("⚠️ Le traitement n'a renvoyé aucune donnée.")
        return
    if df.empty: 
        st.info("ℹ️ Tableau vide, rien à sauvegarder.")
        return
    
    df_export = pd.DataFrame()
    if 'Date_Ref' in df.columns: df_export['Date'] = df['Date_Ref']
    elif 'Date' in df.columns: df_export['Date'] = df['Date']
    else: df_export['Date'] = pd.NaT

    for c in COLS_SQL:
        if c != 'Date' and c != 'isActive' and c != 'Motif':
            df_export[c] = df.get(c, None)

    df_export['Date'] = pd.to_datetime(df_export['Date'], errors='coerce')
    for c in ['Poids_Terrain', 'Poids_Facture', 'Ecart']:
        df_export[c] = pd.to_numeric(df_export[c], errors='coerce').fillna(0)
    
    if 'Num Ticket' in df_export.columns and 'Exutoire' in df_export.columns:
        subset_cols = ['Num Ticket', 'Exutoire', 'Num Bon'] if 'Num Bon' in df_export.columns else ['Num Ticket', 'Exutoire']
        df_export = df_export.drop_duplicates(subset=subset_cols, keep='last')

    if 'Num Bon' in df_export.columns:
        df_export['Num Bon'] = df_export['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

    df_export = df_export.astype(object).where(pd.notnull(df_export), None)
    df_export['isActive'] = True

    rows = df_export.to_dict(orient='records')
    if not rows: return

    try:
        metadata = MetaData()
        target_table = Table(TABLE_NAME, metadata, autoload_with=engine)
        
        with engine.connect() as conn:
            if 'Exutoire' in df_export.columns and 'Num Bon' in df_export.columns:
                unique_bons_suez = df_export[
                    (df_export['Exutoire'] == 'SUEZ') & 
                    (df_export['Num Bon'].notna()) & 
                    (df_export['Num Bon'] != '')
                ]['Num Bon'].unique().tolist()
                
                if unique_bons_suez:
                    conn.execute(
                        text(f"DELETE FROM {TABLE_NAME} WHERE \"Exutoire\" = 'SUEZ' AND \"Num Bon\" IN :bons"),
                        {"bons": tuple(unique_bons_suez)}
                    )

            stmt = insert(target_table).values(rows)
            conflict_cols = ['Num Ticket', 'Exutoire', 'Num Bon']
            update_dict = {c.name: c for c in stmt.excluded if c.name not in conflict_cols}
            update_dict['isActive'] = True 
            
            
            stmt = stmt.on_conflict_do_update(
                index_elements=['Num Ticket', 'Exutoire', 'Num Bon'],
                set_=update_dict
            )
            result = conn.execute(stmt)
            conn.commit()
            st.success(f"✅ Données sauvegardées avec succès ({result.rowcount} lignes traitées).")
                
    except Exception as e:
        logger.error(f"Erreur Sauvegarde DB: {e}", exc_info=True)
        st.error(f"Erreur Technique : {e}")

# =============================================================================
# MODULE DUPILLE
# =============================================================================

def charger_dupille(f):
    try:
        # Heuristic for detecting the header row (Terrain DUPILLE JAN26.xls)
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num ticket" in row_str and "date" in row_str:
                idx = i; break
                
        f.seek(0)
        df = pd.read_excel(f, header=idx) # [FIX] Remove dtype=str to allow proper Date/Float reading
        
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            # Mapping based on "DUPILLE JAN26.xls"
            if "num bon" in cl: cols[c] = "Num Bon"
            if "chauffeur" in cl: cols[c] = "Chauffeur"
            if "immatriculation" in cl or "matière" in cl: 
                # Be careful, "Immatriculation" is column 3, "Description" (Matiere) is col 4
                if "immat" in cl: cols[c] = "Immatriculation"
                elif "description" in cl: cols[c] = "Matiere_T"
            
            # Explicit checks if ambiguous
            if "description" in cl: cols[c] = "Matiere_T"
            
            if "num ticket" in cl:
                if "2" in cl: cols[c] = "Num Ticket 2"
                else: cols[c] = "Num Ticket"
            
            if "nchantier" in cl: cols[c] = "Client"
            
            if "poids" in cl and "tonnes" in cl: cols[c] = "Poids_Terrain"
            
            if "date" in cl and "jour" not in cl: cols[c] = "Date_Ref"
            
        df = df.rename(columns=cols)
        
        # [FIX] Ensure text columns are strings
        for txt_col in ["Num Ticket", "Num Ticket 2", "Client", "Chauffeur", "Immatriculation", "Matiere_T", "Num Bon"]:
            if txt_col in df.columns:
                df[txt_col] = df[txt_col].astype(str).replace('nan', '')
            
            if "nchantier" in cl: cols[c] = "Client"
            
            if "poids" in cl and "tonnes" in cl: cols[c] = "Poids_Terrain"
            
            if "date" in cl and "jour" not in cl: cols[c] = "Date_Ref"
            
        df = df.rename(columns=cols)
        
        # [FIX] Ensure text columns are strings
        for txt_col in ["Num Ticket", "Num Ticket 2", "Client", "Chauffeur", "Immatriculation", "Matiere_T", "Num Bon"]:
            if txt_col in df.columns:
                df[txt_col] = df[txt_col].astype(str).replace('nan', '')

        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
            
        # [USER REQUEST] Strict parsing
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)

        return df
    except Exception as e:
        logger.error(f"Erreur charger_dupille: {e}")
        return pd.DataFrame()



def charger_dupille_facture(f_fac):
    """
    Charger les factures Dupille multi-onglets (CLIENTS PRIVES, CU GPSEO, etc.).
    Fusionne les onglets sur la base des colonnes communes.
    """
    try:
        xls = pd.ExcelFile(f_fac)
        all_sheets = []
        
        for sheet_name in xls.sheet_names:
            # Lire un échantillon pour trouver le header
            df_sample = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=15)
            header_idx = None
            for i, row in df_sample.iterrows():
                row_str = str(row.values).lower()
                if any(k in row_str for k in ['net', 'poids']) and any(k in row_str for k in ['id', 'ticket']):
                    header_idx = i
                    break
            
            if header_idx is not None:
                # Seek back not needed for ExcelFile read
                df = pd.read_excel(xls, sheet_name=sheet_name, header=header_idx, dtype=str)
                df = df.dropna(how='all', axis=1)
                df['Original_Sheet_Name'] = str(sheet_name) # [NEW] Capture sheet name for Activity
                all_sheets.append(df)
            else:
                # Fallback: try reading with header=0
                df = pd.read_excel(xls, sheet_name=sheet_name, header=0, dtype=str)
                df['Original_Sheet_Name'] = str(sheet_name) # [NEW] Capture sheet name for Activity
                all_sheets.append(df)

        if not all_sheets:
            return pd.DataFrame()
            
        # Fusionner - pandas concat aligne automatiquement les colonnes par nom
        df_final = pd.concat(all_sheets, ignore_index=True)
        return df_final
        
    except Exception as e:
        st.error(f"Erreur chargement facture Dupille: {e}")
        return pd.DataFrame()

def process_dupille(f_lb, f_fac):
    # 1. Charger Terrain
    df_lb = charger_dupille(f_lb)
    if df_lb.empty: return pd.DataFrame()

    # [FIX] Apply date repair to Terrain data
    if 'Date_Ref' in df_lb.columns:
         # [USER REQUEST] Force DD/MM/YYYY parsing via robust function
         # Already done in charger_dupille, but strictly ensuring it here if needed or just pass
         pass
         
         # Use Jour column if available (DUPILLE specific)
         # Column 'Jour' might be present? check charger_dupille
         # It's not explicitly renamed in charger_dupille so it should be "Jour" or similar
         
         # Find 'Jour' col with case insensitivity
         j_col = None
         for c in df_lb.columns:
             if str(c).lower().strip() == 'jour':
                 j_col = c; break
         
         # [NEW] Merge Num Ticket 2 if exists
         if 'Num Ticket 2' in df_lb.columns and 'Num Ticket' in df_lb.columns:
             df_lb['Num Ticket'] = df_lb['Num Ticket'].fillna(df_lb['Num Ticket 2'])
         elif 'Num Ticket 2' in df_lb.columns and 'Num Ticket' not in df_lb.columns:
             df_lb['Num Ticket'] = df_lb['Num Ticket 2']
         
         if j_col:
             # Clean Jour column: Handle "nan", empty, whitespace
             df_lb[j_col] = df_lb[j_col].astype(str).replace(r'^\s*$', np.nan, regex=True).replace(['nan', 'NaN', 'None'], np.nan)
             df_lb[j_col] = df_lb[j_col].ffill()
             
             # [USER REQUEST] Disable repair heuristic
             # df_lb = repair_dates_with_jour(df_lb, 'Date_Ref', j_col, "DUPILLE LB")
             pass
         else:
             # Fallback? No, do NOT use median/majority month as it causes false positives
             pass
    
    # 2. Charger Facture
    df_fac = charger_dupille_facture(f_fac)
    
    # [USER REQUEST] Ignore "COLONNE..."
    cols_to_drop = [c for c in df_fac.columns if "COLONNE" in str(c).upper()]
    if cols_to_drop:
        df_fac = df_fac.drop(columns=cols_to_drop)
        
    # Map Facture
    nc = {}
    for c in df_fac.columns:
        cl = str(c).lower().strip()
        
        if "ticket" in cl or cl == "id": nc[c] = "Num Ticket"
        elif "net" in cl: nc[c] = "Poids_Facture" 
        elif "poids" in cl and "facture" in cl: nc[c] = "Poids_Facture"
        
        # [USER REQUEST] EXT Client = lib_zone
        elif "zone" in cl or "lib_zone" in cl: nc[c] = "Client"  # Used to be Zone, now Client (EXT)
        elif "client" in cl or "lib_client" in cl: nc[c] = "Ref_Client" # Backup info
        
        elif "code matière" in cl or "lib_produit" in cl: nc[c] = "EXT_Matiere"
        elif "matière" in cl or "produit" in cl: nc[c] = "EXT_Matiere"
        
        elif "immatriculation" in cl or "véhicule" in cl: nc[c] = "Immatriculation"
        elif "transporteur" in cl or "lib_transporteur" in cl: nc[c] = "Transporteur"
        
        # [NEW] Detect Num Bon in Invoice
        elif "bordereau" in cl or "bon de" in cl or (cl.startswith("n") and cl.endswith("bon")): nc[c] = "Num Bon"
        elif "n° bon" in cl or "num bon" in cl or "bon n" in cl: nc[c] = "Num Bon"

        # Zone is now Client
        elif "date" in cl or "dates" in cl: nc[c] = "Date_Ref"
        # Map sheet name to Activité
        elif "original_sheet_name" in cl: nc[c] = "Activité"
        
    df_fac = df_fac.rename(columns=nc)
    
    # Handle multiple columns mapping to the same name (e.g. 'net' and 'net (kg)')
    # by coalescing them into one, instead of just dropping duplicates.
    target_names = ["Num Ticket", "Poids_Facture", "Client", "EXT_Matiere", "Immatriculation", "Transporteur", "Date_Ref", "Num Bon", "Activité"]
    for target in target_names:
        cols_indices = [j for j, name in enumerate(df_fac.columns) if name == target]
        if len(cols_indices) > 1:
            # We have duplicates. Coalesce them.
            combined = df_fac.iloc[:, cols_indices[0]].copy()
            for idx in cols_indices[1:]:
                combined = combined.fillna(df_fac.iloc[:, idx])
            
            # Drop all columns by that name
            df_fac = df_fac.loc[:, df_fac.columns != target].copy()
            # Add back the combined one
            df_fac[target] = combined

    # Filter: Client (was Zone) must NOT contain "DECHETTERIE PROFESSIONNEL"
    # Note: File often has "PROFESSIONNEL" (2 Ns). Code might have had 1 N.
    if "Client" in df_fac.columns:
        df_fac['Client'] = df_fac['Client'].astype(str).str.upper()
        # Regex to handle PROFESSIONEL or PROFESSIONNEL
        df_fac = df_fac[~df_fac['Client'].str.contains(r"DECHETTERIE PROFESSION+EL", regex=True, na=False)]

    # Filter for SOTREMA if Transporteur column exists
    if "Transporteur" in df_fac.columns:
        df_fac['Transporteur'] = df_fac['Transporteur'].astype(str).str.upper()
        # Keep only SOTREMA (or empty if lenient, but user asked specifically for SOTREMA)
        # Using containment to be safe (e.g. "SOTREMA 78")
        df_fac = df_fac[df_fac['Transporteur'].str.contains("SOTREMA", na=False)]
    
    # Weight Conversion (kg -> T) if explicitly likely
    if "Poids_Facture" in df_fac.columns:
        p_f = df_fac.get('Poids_Facture', pd.Series(0, index=df_fac.index))
        p = pd.to_numeric(p_f, errors='coerce').fillna(0)
        # Heuristic: if mean > 50, it's kg
        if p.mean() > 50: p = p / 1000.0
        df_fac["Poids_Facture"] = p
        
    if 'Date_Ref' in df_fac.columns:
        # [USER REQUEST] Force DD/MM/YYYY parsing via robust function
        df_fac['Date_Ref'] = df_fac['Date_Ref'].apply(convertir_date_robuste)

    if 'Client' in df_fac.columns:
        df_fac['Client'] = df_fac['Client'].apply(normaliser_client_dupille)
        
    if 'EXT_Matiere' in df_fac.columns:
        df_fac['EXT_Matiere'] = df_fac['EXT_Matiere'].apply(normaliser_matiere_dupille)
        
    # df_fac['Activité'] = 'DUPILLE_FAC' # [REMOVED] Use sheet name instead if available
    if 'Activité' not in df_fac.columns:
        df_fac['Activité'] = 'DUPILLE_FAC' # Fallback only

    if 'Num Ticket' in df_fac.columns:
        df_fac['Num Ticket'] = df_fac['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace(['nan', 'None', '', 'NAN'], np.nan)

    # [NEW] Inject Num Bon from Terrain into Invoice if missing
    if 'Num Ticket' in df_lb.columns and 'Num Bon' in df_lb.columns:
        # Create mapping Ticket -> Bon (only valid, non-empty Bons)
        clean_lb = df_lb.dropna(subset=['Num Ticket', 'Num Bon']).copy()
        clean_lb['Num Ticket'] = clean_lb['Num Ticket'].astype(str).str.strip()
        clean_lb['Num Bon'] = clean_lb['Num Bon'].astype(str).str.strip()
        
        t_to_b = dict(zip(clean_lb['Num Ticket'], clean_lb['Num Bon']))
        
        # Inject into Facture
        if 'Num Bon' not in df_fac.columns:
            df_fac['Num Bon'] = np.nan
        
        # Fill missing Bons in Facture using Terrain mapping
        # Fill missing Bons in Facture using Terrain mapping
        import re
        def fill_bon(row):
            b = str(row.get('Num Bon', '')).strip().upper()
            if b not in ['', 'NAN', 'NONE', '0']:
                return row.get('Num Bon')
            
            # Try to find Bon from Ticket(s)
            t_str = str(row.get('Num Ticket', '')).upper().strip()
            if not t_str or t_str in ['NAN', 'NONE']: return np.nan
            
            # Split by common separators: space, comma, slash, plus, dash
            # Be careful with dash if tickets contain dashes, but usually they are numeric
            # Dupille tickets seem to be numeric.
            tokens = re.split(r'[ \/,+\-]+', t_str)
            
            for token in tokens:
                token = token.strip()
                if not token: continue
                # Lookup
                found_b = t_to_b.get(token)
                if found_b: return found_b # Return first match
            
            return np.nan
            
        df_fac['Num Bon'] = df_fac.apply(fill_bon, axis=1)

    # [USER REQUEST] Aggregate multiple tickets for one bon
    def aggregate_dupille_df(df, type_suffix):
        if 'Num Bon' not in df.columns: return df
        # Clean Bon for grouping; [NEW] Strip leading zeros "0123" -> "123"
        df['AGG_BON'] = df['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', '', 'NONE'], np.nan)
        
        # Split: rows with valid BON for aggregation
        mask_bon = df['AGG_BON'].notna()
        df_to_agg = df[mask_bon].copy()
        df_rest = df[~mask_bon].copy()
        
        if df_to_agg.empty: return df
        
        p_col = 'Poids_Terrain' if 'Poids_Terrain' in df.columns else 'Poids_Facture'
        m_col = 'Matiere_T' if 'Matiere_T' in df.columns else 'EXT_Matiere'
        
        # Define grouping columns (common fields that should match for same bon)
        # [FIX] Group strictly by BON to handle multi-ticket bonuses even if dates/clients differ slightly
        group_cols = ['AGG_BON']
        # if 'Activité' in df_to_agg.columns: group_cols.append('Activité') # Keep Activity separate? Unlikely same Bon spans activities.
        
        # Intersect with existing columns
        group_cols = [c for c in group_cols if c in df_to_agg.columns]
        
        # Perform Aggregation
        agg_rules = {
            p_col: 'sum',
            'Num Ticket': lambda x: ' / '.join(filter(None, [str(v) for v in sorted(list(set(x)))]))
        }
        # Add remaining columns with 'first'
        for c in df_to_agg.columns:
            if c not in group_cols and c not in agg_rules and c != 'AGG_BON':
                agg_rules[c] = 'first'
        
        df_agg = df_to_agg.groupby(group_cols, as_index=False).agg(agg_rules)
        
        # Cleanup
        final_df = pd.concat([df_agg, df_rest], ignore_index=True)
        if 'AGG_BON' in final_df.columns: final_df = final_df.drop(columns=['AGG_BON'])
        return final_df

    df_lb = aggregate_dupille_df(df_lb, "_T")
    df_fac = aggregate_dupille_df(df_fac, "_F")

    # 3. Matching Logic (Standard)
    # -------------------------------------------------------------------------
    def get_strict_key(row):
        t = str(row.get('Num Ticket', '')).strip().upper()
        if t in ['ST', 'NAN', '', 'NONE', '0', 'None', 'NAT']: return np.nan
        return t

    df_lb['K'] = df_lb.apply(get_strict_key, axis=1)
    df_fac['K'] = df_fac.apply(get_strict_key, axis=1)
    
    # IDs for tracking
    df_lb['_TMP_ID'] = df_lb.index
    df_fac['_TMP_ID'] = df_fac.index
    
    # 1. Match Exact
    m1 = pd.merge(df_lb.dropna(subset=['K']), df_fac.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_lb[~df_lb['K'].isin(ids_t)].copy()
    l_ref = df_fac[~df_fac['K'].isin(ids_f)].copy()
    
    # 2. Match Bon (if present)
    match2 = pd.DataFrame()
    if 'Num Bon' in l_ter.columns and 'Num Bon' in l_ref.columns:
         # Need clean bons; [NEW] Strip leading zeros
         l_ter['B_K'] = l_ter['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', ''], np.nan)
         l_ref['B_K'] = l_ref['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', ''], np.nan)
         
         m2 = pd.merge(l_ter.dropna(subset=['B_K']), l_ref.dropna(subset=['B_K']), on='B_K', how='inner', suffixes=('_T', '_F'))
         # Drop duplicates/Validate?
         if not m2.empty:
             match2 = m2.drop_duplicates(subset=['B_K'])
             match2['Methode'] = '1. Bon Exact'
             match2['_merge'] = 'both'
             
             ids_t2 = match2['_TMP_ID_T'].unique()
             ids_f2 = match2['_TMP_ID_F'].unique()
             l_ter = l_ter[~l_ter['_TMP_ID'].isin(ids_t2)]
             l_ref = l_ref[~l_ref['_TMP_ID'].isin(ids_f2)]

    # 3. Smart Match (Date + Poids)
    match3_smart = pd.DataFrame()
    # Ensure all required match columns exist
    has_poids_t = 'Poids_Terrain' in l_ter.columns
    has_poids_f = 'Poids_Facture' in l_ref.columns
    has_date_t = 'Date_Ref' in l_ter.columns
    has_date_f = 'Date_Ref' in l_ref.columns
    
    if not l_ter.empty and not l_ref.empty and has_poids_t and has_poids_f and has_date_t and has_date_f:
        cols_t = ['_TMP_ID', 'Key_Date', 'Poids_Terrain', 'Key_Site_T', 'Client', 'Matiere_T', 'Num Ticket', 'Num Bon']
        cols_f = ['_TMP_ID', 'Key_Date', 'Poids_Facture', 'Key_Site_F', 'Client', 'EXT_Matiere', 'Num Ticket', 'Num Bon']      
        # Standard smart match logic
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
         
        # [FIX] Avoid merging on "NAN"
        l_ter_valid = l_ter[l_ter['Key_Date'] != "NAN"].copy()
        l_ref_valid = l_ref[l_ref['Key_Date'] != "NAN"].copy()

        if not l_ter_valid.empty and not l_ref_valid.empty:
            m3 = pd.merge(l_ter_valid, l_ref_valid, on='Key_Date', suffixes=('_T', '_F'))
        else:
            m3 = pd.DataFrame()
        if not m3.empty:
            m3['Delta'] = abs(pd.to_numeric(m3['Poids_Terrain'], errors='coerce') - pd.to_numeric(m3['Poids_Facture'], errors='coerce'))
            cands = m3[m3['Delta'] <= 0.02].sort_values('Delta')
            if not cands.empty:
                match3_smart = cands.drop_duplicates(subset=['_TMP_ID_T'], keep='first').drop_duplicates(subset=['_TMP_ID_F'], keep='first')
                match3_smart['Methode'] = '2. Smart Match'
                match3_smart['_merge'] = 'both'
                 
                # Cleanup
                ids_t3 = match3_smart['_TMP_ID_T'].unique()
                ids_f3 = match3_smart['_TMP_ID_F'].unique()
                l_ter = l_ter[~l_ter['_TMP_ID'].isin(ids_t3)]
                l_ref = l_ref[~l_ref['_TMP_ID'].isin(ids_f3)]
    
    # 4. Final Concat
    cols_t = df_lb.columns
    cols_f = df_fac.columns
    
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f})
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    final = pd.concat([match1, match2, match3_smart, orph_t, orph_f], ignore_index=True)
    
    # Consolidation
    final['Exutoire'] = "DUPILLE"
    
    if 'Num Ticket_F' in final.columns:
        # Prefer Terrain Ticket IDs (which may be concatenated) for Dupille
        # Also ensure Num Ticket from Terrain (Num Ticket_T) handles Num Ticket 2 if it wasn't merged earlier (though it should be)
        t_id = final['Num Ticket_T']
        if 'Num Ticket 2_T' in final.columns:
             t_id = t_id.fillna(final['Num Ticket 2_T'])
             
        final['Num Ticket'] = t_id.fillna(final.get('Num Ticket_F')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
        
    final['Num Bon'] = resolve_col(final, 'Num Bon')
    final['Date_Ref'] = resolve_col(final, 'Date_Ref')
    
    # [FIX] Coalesce weights correctly (handle _T / _F suffixes from merges)
    # Poids Terrain
    p_t = pd.Series(np.nan, index=final.index)
    if 'Poids_Terrain' in final.columns: p_t = p_t.fillna(final['Poids_Terrain'])
    if 'Poids_Terrain_T' in final.columns: p_t = p_t.fillna(final['Poids_Terrain_T'])
    final['Poids_Terrain'] = pd.to_numeric(p_t, errors='coerce').fillna(0)
    
    # Poids Facture
    p_f = pd.Series(np.nan, index=final.index)
    if 'Poids_Facture' in final.columns: p_f = p_f.fillna(final['Poids_Facture'])
    if 'Poids_Facture_F' in final.columns: p_f = p_f.fillna(final['Poids_Facture_F'])
    final['Poids_Facture'] = pd.to_numeric(p_f, errors='coerce').fillna(0)
    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    
    final['INT Client'] = final.get('Client_T', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    final['EXT Client'] = final.get('Client_F', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    
    final['Matiere_T'] = resolve_col(final, 'Matiere_T')
    final['EXT_Matiere'] = resolve_col(final, 'EXT_Matiere')
    # [FIX] Resolve Activité: Prioritize Facture (Sheet Name) for Dupille
    final['Activité'] = final.get('Activité_F', pd.Series(np.nan, index=final.index)).fillna(final.get('Activité', pd.Series(np.nan, index=final.index))).fillna(final.get('Activité_T', pd.Series(np.nan, index=final.index))).fillna("DECH_DUPILLE")
    
    # Immat Coalesce (Global Fix Standard)
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final)))
    c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final)))
    c_ch_f = final.get('Chauffeur_F', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f).astype(str).replace(['nan', 'NAN', 'None'], '')

    c_im = final.get('Immatriculation', pd.Series([np.nan]*len(final)))
    c_im_t = final.get('Immatriculation_T', pd.Series([np.nan]*len(final)))
    c_im_f = final.get('Immatriculation_F', pd.Series([np.nan]*len(final)))
    final['Immatriculation'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace(['nan', 'NAN', 'None'], '')

    final['Immatriculation'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace(['nan', 'NAN', 'None'], '')

    # [FIX] Normalize Terrain Matiere too
    if 'Matiere_T' in final.columns:
         final['Matiere_T'] = final['Matiere_T'].apply(normaliser_matiere_dupille)

    # Verifications
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    
    def check_mat_dupille(row):
        if row['_merge'] != 'both': return '' # Empty if not matched, to avoid confusion with Pb.Ext column
        m_t = str(row.get('Matiere_T', '')).upper().strip()
        m_f = str(row.get('EXT_Matiere', '')).upper().strip()
        if not m_t or m_t == 'NAN': return 'Pb.Mat' # Missing info
        
        # Direct Match
        if m_t == m_f: return 'OK'
        # Loose Match
        if m_t in m_f or m_f in m_t: return 'OK'
        
        return 'Pb.Mat'

    final['Verif_Matiere'] = final.apply(check_mat_dupille, axis=1)
    # Use existing helper `check_client_dupille_strict` if defined or inline
    # Assuming helper exists from previous code (it was in the file)
    
    # Normalize site keys for check
    final['Key_Site_T_FINAL'] = final['INT Client'].apply(normalize_site_key)
    final['Key_Site_F_FINAL'] = final['EXT Client'].apply(normalize_site_key)
    
    def check_client_dupille_strict(row):
        k_t = row.get('Key_Site_T_FINAL')
        k_f = row.get('Key_Site_F_FINAL')
        if check_site_keys({'Key_Site_T': k_t, 'Key_Site_F': k_f}):
            return 'OK'
        c_int = str(row.get('INT Client', '')).upper()
        c_ext = str(row.get('EXT Client', '')).upper()
        
        # [USER REQUEST] Ignore Pb.Clt if EXT Client contains numbers
        if any(char.isdigit() for char in c_ext): return "OK"
        
        if "GPSEO" in c_int and "GPSO" in c_ext: return "OK"
        if "GPSO" in c_int and "GPSEO" in c_ext: return "OK"
        return 'Pb.Clt'

    final['Verif_Client'] = final.apply(check_client_dupille_strict, axis=1)
    
    return final


from modules.verif_suez import restore_columns
# (restore_columns moved to modules/verif_suez.py)

def filter_and_split_rejects(merged_df, original_cols_ter, original_cols_ref):
    if merged_df.empty: return merged_df, pd.DataFrame(), pd.DataFrame()
    c_int = 'Client_T' if 'Client_T' in merged_df.columns else 'Client'
    c_ext = 'TEMP_CodeAdresse_F' if 'TEMP_CodeAdresse_F' in merged_df.columns else 'TEMP_CodeAdresse'
    mask_ok = merged_df.apply(lambda r: check_client_compatibility(r, c_int, c_ext), axis=1)
    valid = merged_df[mask_ok].copy()
    rejected = merged_df[~mask_ok].copy()
    if rejected.empty: return valid, pd.DataFrame(), pd.DataFrame()
    rej_ter = restore_columns(rejected, '_T', original_cols_ter)
    rej_ref = restore_columns(rejected, '_F', original_cols_ref)
    return valid, rej_ter, rej_ref

def process_picheta(f_ctc, f_dech, f_exp):
    logger.info("Début traitement PICHETA GPSEO")
    dfs = []
    if f_ctc: dfs.append(charger_picheta(f_ctc, "CTC"))
    if f_dech: dfs.append(charger_picheta(f_dech, "DECH"))
    
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)

    temp = pd.read_excel(f_exp, header=None, nrows=20)
    idx_ref = 0
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        if "document" in row_str and "date" in row_str: idx_ref = i; break
        if "n° bon" in row_str and "date" in row_str: idx_ref = i; break
            
    f_exp.seek(0)
    df_ref = pd.read_excel(f_exp, header=idx_ref, dtype=str) 
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower()
        if "document" in cl or "n° bon" in cl: cols_ref[c] = "Num Ticket"
        if "q liv" in cl or "poids" in cl: cols_ref[c] = "Poids_Facture"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "immat" in cl: cols_ref[c] = "Immatriculation"
    
    df_ref = df_ref.rename(columns=cols_ref)
    
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
    
    if 'TEMP_CodeAdresse' in df_ref.columns:
        df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETTERIE PICHETA')
    else:
        df_ref['Client'] = "DECHETTERIE PICHETA"

    df_ref['EXT_Matiere'] = "GRAVATS"
    
    # [FIX] Apply date repair to Invoice data as well
    # [USER REQUEST] Strict parsing
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        # NETTOYAGE SPECIFIQUE PICHETA (Suppression des lignes de sous-titres "Libellé interne...")
        mask_garbage = df_ref['Num Ticket'].astype(str).str.contains("Libellé|source", case=False, na=False)
        df_ref = df_ref[~mask_garbage]
        
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

    def get_strict_key(row):
        t = str(row.get('Num Ticket', '')).strip().upper()
        b = str(row.get('Num Bon', '')).strip().upper()
        vides = ['ST', 'NAN', '', 'NONE', '0', 'None']
        if t not in vides: return t
        if b not in vides: return b
        return np.nan

    df_ter['K'] = df_ter.apply(get_strict_key, axis=1)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace('NAN', np.nan).replace('', np.nan)

    cols_ter = df_ter.columns
    cols_ref = df_ref.columns

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    
    matched_ids_t = match1['K'].unique()
    matched_ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(matched_ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(matched_ids_f)].copy()

    match2 = pd.DataFrame()

    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")

        l_ter['Key_Site'] = l_ter['Client'].apply(normalize_site_key)
        l_ref['Key_Site'] = l_ref['Client'].apply(normalize_site_key)

        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta_Poids'] = (p_t - p_f).abs()
            
            candidates = m_cross[m_cross['Delta_Poids'] <= 0.5].copy()
            
            if not candidates.empty:
                pass 
            
            candidates = candidates.sort_values('Delta_Poids')
            
            if 'Num Bon' in candidates.columns:
                match2 = candidates.drop_duplicates(subset=['Num Bon'], keep='first')
            else:
                match2 = candidates.drop_duplicates(subset=['Key_Date', 'Poids_Terrain'], keep='first')
                
            if not match2.empty:
                match2['Methode'] = '2. Smart Match'
                match2['_merge'] = 'both'
                
                if 'Num Ticket_F' in match2.columns:
                    match2['Num Ticket'] = match2['Num Ticket_F']
                
                matched_tickets_fac = match2['Num Ticket_F'].tolist() if 'Num Ticket_F' in match2.columns else []
                
                match2['_UID_EXCL'] = match2['Key_Date'].astype(str) + "_" + match2['Poids_Terrain'].astype(str)
                l_ter['_UID_EXCL'] = l_ter['Key_Date'].astype(str) + "_" + l_ter['Poids_Terrain'].astype(str)
                
                matched_uids_ter = match2['_UID_EXCL'].tolist()
                
                final_t = l_ter[~l_ter['_UID_EXCL'].isin(matched_uids_ter)]
                
                if 'Num Ticket' in l_ref.columns:
                    final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_fac)]
                else:
                    final_f = l_ref
            else:
                final_t = l_ter
                final_f = l_ref
        else:
            final_t = l_ter
            final_f = l_ref
    else:
        final_t = l_ter
        final_f = l_ref

    if '_UID_EXCL' in final_t.columns: final_t = final_t.drop(columns=['_UID_EXCL'])
    if '_UID_EXCL' in match2.columns: match2 = match2.drop(columns=['_UID_EXCL'])

    # --- PHASE 3 : SMART MATCH FLEXIBLE (Dates +/- 3 jours, Poids <= 0.5) ---
    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         # Strategy: Explode final_t with date offsets (-3 to +3) then join on Date
         # This avoids Cartesian product and handles large weight diffs (0.5T)
         
         offset_dfs = []
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'], errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'], errors='coerce')
         
         # Clean invalid dates
         f_t_clean = final_t.dropna(subset=['Date_Obj']).copy()
         f_f_clean = final_f.dropna(subset=['Date_Obj']).copy()
         
         if not f_t_clean.empty and not f_f_clean.empty:
             for offset in range(-3, 4):
                 temp = f_t_clean.copy()
                 temp['Join_Date'] = temp['Date_Obj'] + pd.Timedelta(days=offset)
                 temp['_Offset'] = offset
                 offset_dfs.append(temp)
             
             t_expanded = pd.concat(offset_dfs)
             
             # Join on Date
             m_flex = pd.merge(t_expanded, f_f_clean, left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
             
             if not m_flex.empty:
                 m_flex['Delta_Poids'] = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs()
                 m_flex['Delta_Days'] = m_flex['_Offset'].abs()
                 
                 # Criteria: Poids <= 0.5 (User Request)
                 candidates_3 = m_flex[m_flex['Delta_Poids'] <= 0.5].copy()
                 
                 if not candidates_3.empty:
                     # Prioritize smallest date diff, then smallest weight diff
                     candidates_3 = candidates_3.sort_values(['Delta_Days', 'Delta_Poids'])
                     
                     if 'Num Bon' in candidates_3.columns:
                         match3 = candidates_3.drop_duplicates(subset=['Num Bon'], keep='first')
                     else:
                         # Deduplicate carefully
                         match3 = candidates_3.drop_duplicates(subset=['Date_Ref_T', 'Poids_Terrain'], keep='first')
                     
                     if not match3.empty:
                         match3['Methode'] = '3. Match Flex Date'
                         match3['_merge'] = 'both'
                         match3['Date_Ref'] = match3['Date_Ref_T']
                         
                         if 'Num Ticket_F' in match3.columns:
                            match3['Num Ticket'] = match3['Num Ticket_F']
                         
                         # Cleanup and Exclusion logic
                         def make_uid(df, s):
                             return df[f'Num Ticket{s}'].astype(str) + "_" + df[f'Poids_Terrain{"" if s=="_T" else ""}'].astype(str) + "_" + df[f'Date_Ref{s}'].astype(str)

                         matched_uids_t = make_uid(match3, '_T').tolist()
                         matched_uids_f = make_uid(match3, '_F').tolist()
                         
                         final_t['_UID_CLEAN'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str) + "_" + final_t['Date_Ref'].astype(str)
                         final_f['_UID_CLEAN'] = final_f['Num Ticket'].astype(str) + "_" + final_f['Poids_Facture'].astype(str) + "_" + final_f['Date_Ref'].astype(str)
                         
                         final_t = final_t[~final_t['_UID_CLEAN'].isin(matched_uids_t)].drop(columns=['_UID_CLEAN'])
                         final_f = final_f[~final_f['_UID_CLEAN'].isin(matched_uids_f)].drop(columns=['_UID_CLEAN'])
                         
                         cols_to_drop = ['Date_Obj_T', 'Date_Obj_F', 'Join_Date', '_Offset', 'Delta_Days', 'Delta_Poids']
                         for c in cols_to_drop:
                             if c in match3.columns: match3 = match3.drop(columns=[c])
                     
             if 'Date_Obj' in final_t.columns: final_t = final_t.drop(columns=['Date_Obj'])
             if 'Date_Obj' in final_f.columns: final_f = final_f.drop(columns=['Date_Obj'])
    
    final_orph_t = final_t.rename(columns={c: c + '_T' for c in cols_ter})
    final_orph_f = final_f.rename(columns={c: c + '_F' for c in cols_ref})
    
    final_orph_t['_merge'] = 'left_only'; final_orph_t['Methode'] = 'Non Trouvé'
    final_orph_f['_merge'] = 'right_only'; final_orph_f['Methode'] = 'Non Trouvé'

    final = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True)
    
    pass

    final['Exutoire'] = "PICHETA GPSEO"



    # On utilise d'abord le ticket explicite du match (Smart Match), sinon celui résolu via resolve_col
    if 'Num Ticket_F' in final.columns and 'Num Ticket_T' in final.columns:
         # Priorise Num Ticket (provenant du Smart Match) si présent
         t_smart = final['Num Ticket'] if 'Num Ticket' in final.columns else np.nan
         t_f = final['Num Ticket_F']
         t_t = final['Num Ticket_T']
         
         final['Num Ticket'] = t_smart.fillna(t_f).fillna(t_t).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    else:
         final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    
    # Si le ticket est toujours "ST" ou vide, on le garde comme ST, mais si on a trouvé un ticket via Smart Match, il a dû être écrasé ci-dessus
    final['Num Ticket'] = final['Num Ticket'].astype(str).replace(r'(?i)^\s*ST\s*$', np.nan, regex=True).fillna('ST')
    
    c_nb = final.get('Num Bon', pd.Series([np.nan]*len(final)))
    c_nb_t = final.get('Num Bon_T', pd.Series([np.nan]*len(final)))
    c_nb_f = final.get('Num Bon_F', pd.Series([np.nan]*len(final)))
    final['Num Bon'] = c_nb.fillna(c_nb_t).fillna(c_nb_f).astype(str).replace(['nan', 'NAN', 'None'], '')

    final['Date_Ref'] = resolve_col(final, 'Date_Ref')

    c_im = final.get('Immatriculation', pd.Series([np.nan]*len(final)))
    c_im_t = final.get('Immatriculation_T', pd.Series([np.nan]*len(final)))
    c_im_f = final.get('Immatriculation_F', pd.Series([np.nan]*len(final)))
    final['Immatriculation'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace(['nan', 'NAN', 'None'], '')
    
    p_ter = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    p_ter_t = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(p_ter > 0, p_ter, p_ter_t)
    
    p_fac = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    p_fac_f = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(p_fac > 0, p_fac, p_fac_f)
    
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] >= 99, 0, final['Poids_Terrain'])
    final['Poids_Facture'] = np.where(final['Poids_Facture'] >= 99, 0, final['Poids_Facture'])

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    
    final['Activité'] = resolve_col(final, 'Activité').fillna('PICHETA GPSEO')
    
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final)))
    c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final)))
    c_ch_f = final.get('Chauffeur_F', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f).astype(str).replace(['nan', 'NAN', 'None'], '')

    final['INT Client'] = resolve_col(final, 'Client').fillna("GPSEO").astype(str).replace(['nan', 'NAN', 'None'], '') # Client_T
    final['Client'] = "GPSEO"
    
    c_F_clean = final.get('Client_F', final.get('TEMP_CodeAdresse_F', pd.Series([np.nan]*len(final))))
    final['EXT Client'] = c_F_clean.fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')

    final['Matiere_T'] = resolve_col(final, 'Matiere_T').fillna('GRAVATS')
    final['EXT_Matiere'] = 'GRAVATS'
    
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Verif_Client'] = final.apply(lambda r: "OK" if check_client_compatibility(r, 'INT Client', 'EXT Client') else "Pb.Clt", axis=1)

    if 'Num Bon' in final.columns:
        final['Num Bon'] = final['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    return final


def charger_picheta(f, source):
    temp = pd.read_excel(f, header=None, nrows=20)
    best_idx = 0
    max_score = 0
    keywords = ['ticket', 'tp manuel', 'bon', 'nature', 'date', 'poids', 'quantite', 'tonnages', 'immat', 'client', 'chantier']
    
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        score = 0
        for k in keywords:
            if k in row_str: score += 1
        
        if score > max_score:
            max_score = score
            best_idx = i
            
    idx = best_idx
    f.seek(0)
    df = pd.read_excel(f, header=idx, dtype=str)
    cols = {}
    col_date_found = False
    for c in df.columns:
        cl = str(c).lower().strip()
        if "tp manuel" in cl: cols[c] = "Num Ticket"
        if cl in ["quantiteligne", "tonnages"]: cols[c] = "Poids_Terrain"
        if "nature" in cl or "description" in cl: cols[c] = "Matiere_T"
        if cl == "date": cols[c] = "Date_Ref"; col_date_found = True
        elif "date" in cl and not col_date_found and "saisie" not in cl: cols[c] = "Date_Ref"
        if "nchantier" in cl: cols[c] = "Client" 
        elif "exutoire" in cl and "Client" not in cols.values(): cols[c] = "Client" 
        if "bon" in cl and "nbr" not in cl: cols[c] = "Num Bon"
        if "immat" in cl: cols[c] = "Immatriculation"
        if "chauffeur" in cl or "conducteur" in cl: cols[c] = "Chauffeur"
    df = df.rename(columns=cols)
    if "Client" not in df.columns: df["Client"] = f"PICHETA {source}"
    df['Activité'] = source
    if "Poids_Terrain" in df.columns:
        df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
        
    # [USER REQUEST] Strict parsing
    df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
    return df


def charger_valene(f, source):
    try:
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            if "Num Ticket" in str(r.values) or "N° de pesée" in str(r.values): idx = i; break
        f.seek(0); df = pd.read_excel(f, header=idx, dtype=str)
        cols = {}
        for c in df.columns:
            cl = str(c).lower()
            if "ticket" in cl: cols[c] = "Num Ticket"
            if "poids" in cl and "tonnes" in cl: cols[c] = "Poids_Terrain"
            if "poids net" in cl: cols[c] = "Poids_KG"
            if "matière" in cl or "description" in cl: cols[c] = "Matiere_T"
            if "date" in cl: cols[c] = "Date_Ref"
            if "client" in cl: cols[c] = "Client"
            if "bon" in cl: cols[c] = "Num Bon"
            if "chauffeur" in cl or "conducteur" in cl: cols[c] = "Chauffeur"
            if "immat" in cl or "véhicule" in cl: cols[c] = "Immatriculation"
        df = df.rename(columns=cols)
        if "Poids_KG" in df.columns: df["Poids_Terrain"] = pd.to_numeric(df["Poids_KG"], errors='coerce') / 1000
        if "Matiere_T" in df.columns:
             mask_mat = df["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)
             mask_tick = pd.Series([False]*len(df))
             if "Num Ticket" in df.columns:
                 mask_tick = df["Num Ticket"].astype(str).str.contains("total|récap", case=False, na=False)
             
             mask_total = mask_mat | mask_tick
             if mask_total.any():
                 df = df[~mask_total]

        if "Client" not in df.columns: df["Client"] = f"VALENE {source}"
        
        if source == "SOTREMA2" and "Num Ticket" in df.columns:
            s_t = df['Num Ticket'].astype(str).str.strip().str.lower()
            mask_vide = df['Num Ticket'].isna() | (s_t == "") | (s_t == "nan") | (s_t == "none") | (s_t == "0") | (s_t == "0.0")
            
            nb_dropped = mask_vide.sum()
            if nb_dropped > 0:
                df = df[~mask_vide]
        
        df['Activité'] = source
        # [USER REQUEST] Strict parsing
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        logger.info(f"Charge Valene {source}: {len(df)} lignes")
        return df
    except: return pd.DataFrame()

def process_valene(f_pap, f_pav, f_sot, f_exp):
    logger.info("Début traitement VALENE")
    dfs = []
    if f_pap: dfs.append(charger_valene(f_pap, "PAP"))
    if f_pav: dfs.append(charger_valene(f_pav, "PAV"))
    if f_sot: dfs.append(charger_valene(f_sot, "SOTREMA2"))
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)
    try: df_ref = pd.read_excel(f_exp, sheet_name="RPT_RecherchePeseeDetaillee", header=8, dtype=str)
    except: df_ref = pd.read_excel(f_exp, header=8, dtype=str)
    cols_ref = {}
    col_matiere_label = None
    for c in df_ref.columns:
        if str(c).strip().lower() == "matière réalisée": col_matiere_label = c; break
    if not col_matiere_label:
        for c in df_ref.columns:
            cl = str(c).lower().strip()
            if "matière réalisée" in cl and not any(x in cl for x in ["code", "n°", "num", "id", "ref"]): col_matiere_label = c; break
    if col_matiere_label: cols_ref[col_matiere_label] = "EXT_Matiere"
    for c in df_ref.columns:
        if c == col_matiere_label: continue
        cl = str(c).lower().strip()
        if "n° de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "poids" in cl and "net" in cl: cols_ref[c] = "Poids_Facture" 
        elif "poids de la matière" in cl: cols_ref[c] = "Poids_Facture"
        if "date d'entrée" in cl or "date de pesée" in cl: cols_ref[c] = "Date_Ref"
        if "immatriculation" in cl or "véhicule" in cl: cols_ref[c] = "Immatriculation"
    df_ref = df_ref.rename(columns=cols_ref); df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)
    df_ter['Matiere_T'] = df_ter['Matiere_T'].apply(normaliser_matiere_valene)
    if 'EXT_Matiere' in df_ref.columns: df_ref['EXT_Matiere_Norm'] = df_ref['EXT_Matiere'].apply(normaliser_matiere_valene)
    else: df_ref['EXT_Matiere_Norm'] = ""
    merged = pd.merge(df_ter, df_ref, on='Num Ticket', how='outer', indicator=True, suffixes=('_T', '_F'))
    def restaurer_col(df, nom_col):
        if nom_col in df.columns: return df[nom_col].replace(r'^\s*$', np.nan, regex=True).fillna(np.nan)
        col_t, col_f = f"{nom_col}_T", f"{nom_col}_F"
        s_t = df[col_t].replace(r'^\s*$', np.nan, regex=True) if col_t in df.columns else pd.Series([np.nan]*len(df))
        s_f = df[col_f].replace(r'^\s*$', np.nan, regex=True) if col_f in df.columns else pd.Series([np.nan]*len(df))
        return s_t.fillna(s_f)
    c_cl = merged.get('Client', pd.Series([np.nan]*len(merged)))
    c_cl_t = merged.get('Client_T', pd.Series([np.nan]*len(merged)))
    c_cl_f = merged.get('Client_F', pd.Series([np.nan]*len(merged)))
    merged['Client'] = c_cl.fillna(c_cl_t).fillna(c_cl_f)

    c_dt = merged.get('Date_Ref', pd.Series([np.nan]*len(merged)))
    c_dt_t = merged.get('Date_Ref_T', pd.Series([np.nan]*len(merged)))
    c_dt_f = merged.get('Date_Ref_F', pd.Series([np.nan]*len(merged)))
    merged['Date_Ref'] = c_dt.fillna(c_dt_t).fillna(c_dt_f)

    c_ch = merged.get('Chauffeur', pd.Series([np.nan]*len(merged)))
    c_ch_t = merged.get('Chauffeur_T', pd.Series([np.nan]*len(merged)))
    c_ch_f = merged.get('Chauffeur_F', pd.Series([np.nan]*len(merged)))
    merged['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f)

    c_im = merged.get('Immatriculation', pd.Series([np.nan]*len(merged)))
    c_im_t = merged.get('Immatriculation_T', pd.Series([np.nan]*len(merged)))
    c_im_f = merged.get('Immatriculation_F', pd.Series([np.nan]*len(merged)))
    merged['Immatriculation'] = c_im.fillna(c_im_t).fillna(c_im_f)
    merged['Exutoire'] = "VALENE"
    merged['Poids_Terrain'] = np.floor(pd.to_numeric(merged['Poids_Terrain'], errors='coerce').fillna(0) * 100) / 100
    merged['Poids_Facture'] = np.floor(pd.to_numeric(merged['Poids_Facture'], errors='coerce').fillna(0) * 100) / 100
    
    merged['Poids_Terrain'] = np.where(merged['Poids_Terrain'] >= 99, 0, merged['Poids_Terrain'])
    merged['Poids_Facture'] = np.where(merged['Poids_Facture'] >= 99, 0, merged['Poids_Facture'])
    
    merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
    merged['Date_Ref'] = merged['Date_Ref']
    merged['INT Client'] = merged.get('Client_T', merged.get('Client', '')).fillna('')
    merged['EXT Client'] = merged.get('Client_F', '').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})
    merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'})
    merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
    
    merged['INT Client'] = merged['INT Client'].astype(str).replace(['CU GPSO', 'GPSO'], 'GPSEO').replace(['nan', 'NAN', 'None'], '')
    merged['Client'] = merged['Client'].astype(str).replace(['CU GPSO', 'GPSO'], 'GPSEO')

    def verif_client(row):
        c_int = str(row.get('INT Client', '')).upper().strip(); c_ext = str(row.get('EXT Client', '')).upper().strip(); act = str(row.get('Activité', '')).upper()
        if not c_int or not c_ext: return "OK"
        if "SOTREMA2" in act:
            if "GPSEO" not in c_int: return "OK"
        if c_int in ["GPSEO", "CCPIF"] and "CU GRAND PARIS SEINE ET OISE" in c_ext: return "OK"
        if "CU GRAND PARIS SEINE ET OISE" in c_ext and c_int in ["GPSEO", "CCPIF"]: return "OK"
        if c_int in c_ext or c_ext in c_int: return "OK"
        return "Pb.Clt"
    merged['Verif_Client'] = merged.apply(verif_client, axis=1)
    if 'Date' in merged.columns: merged = merged.drop(columns=['Date'])
    merged = merged.rename(columns={'Date_Ref': 'Date'}); cols_final = ['Date', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
    for c in cols_final:
        if c not in merged.columns: merged[c] = ""
    if 'Num Bon' in merged.columns: merged['Num Bon'] = merged['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    return merged[cols_final]


from modules.verif_suez import charger_suez_terrain
# (charger_suez_terrain moved to modules/verif_suez.py)

from modules.verif_suez import process_suez
# Suez logic moved to modules/verif_suez.py


def charger_valoseine(f):
    try:
        # Heuristic to find the header row
        temp = pd.read_excel(f, header=None, nrows=20)
        best_idx = 0
        max_score = 0
        keywords = ['ticket', 'tp manuel', 'bon', 'tonnages', 'date', 'immatriculation', 'chauffeur']
        
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            score = 0
            for k in keywords:
                if k in row_str: score += 1
            if score > max_score:
                max_score = score
                best_idx = i
                
        f.seek(0)
        df = pd.read_excel(f, header=best_idx, dtype=str)
        
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "num bon" in cl: cols[c] = "Num Bon"
            elif "tonnages" in cl: cols[c] = "Poids_Terrain"
            elif "description" in cl: cols[c] = "Matiere_T"
            elif "date" in cl: cols[c] = "Date_Ref"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "immatriculation" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            
        df = df.rename(columns=cols)
        
        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
            
        if "Client" not in df.columns: df["Client"] = "PICHETA VALOSEINE"
        df['Activité'] = "PICHETA VALOSEINE"
        
        # [USER REQUEST] Strict parsing
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Valoseine: {e}")
        st.error(f"Erreur chargement Valoseine: {e}")
        return pd.DataFrame()

def process_valoseine(f_ter, f_fac):
    logger.info("Début traitement PICHETA VALOSEINE")
    
    # 1. Load Terrain
    df_ter = charger_valoseine(f_ter)
    if df_ter.empty: return pd.DataFrame()

    # 2. Load Facture (Export Picheta-like format)
    temp = pd.read_excel(f_fac, header=None, nrows=20)
    idx_ref = 0
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        if "document" in row_str and "date" in row_str: idx_ref = i; break
        if "n° bon" in row_str and "date" in row_str: idx_ref = i; break
            
    f_fac.seek(0)
    df_ref = pd.read_excel(f_fac, header=idx_ref, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower()
        if "document" in cl or "n° bon" in cl: cols_ref[c] = "Num Ticket"
        if "q liv" in cl or "poids" in cl: cols_ref[c] = "Poids_Facture"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "immat" in cl: cols_ref[c] = "Immatriculation"
        if "libellé produit" in cl or "libelle produit" in cl: cols_ref[c] = "EXT_Matiere"
    
    df_ref = df_ref.rename(columns=cols_ref)
    
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
    
    if 'TEMP_CodeAdresse' in df_ref.columns:
        df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETERIE PICHETA VALOSEINE')
    else:
        df_ref['Client'] = "DECHETERIE PICHETA VALOSEINE"

    if 'EXT_Matiere' not in df_ref.columns:
        df_ref['EXT_Matiere'] = "GRAVATS" # Fallback
    
    # Apply Normalization
    if 'Matiere_T' in df_ter.columns:
        df_ter['Matiere_T'] = df_ter['Matiere_T'].apply(normaliser_matiere_picheta_valoseine)
    if 'EXT_Matiere' in df_ref.columns:
        df_ref['EXT_Matiere'] = df_ref['EXT_Matiere'].apply(normaliser_matiere_picheta_valoseine)
    
    # Date Repair for Invoice
    # [USER REQUEST] Strict parsing
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    # Clean Ticket numbers
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        # Filter out "Code produit:" header lines and "Total" lines
        # "Code produ" handles potential truncation
        mask_garbage = df_ref['Num Ticket'].astype(str).str.contains("Libellé|source|Code produ|Total", case=False, na=False)
        df_ref = df_ref[~mask_garbage]
        
        # Filter out empty ticket lines (likely sub-totals where only weight is present)
        # But be careful not to remove valid lines that might just miss a ticket number (though unlikely here as Ticket is key)
        # In this file structure, valid lines always have a date. Sub-total lines usually don't.
        if 'Date_Ref' in df_ref.columns:
             df_ref = df_ref.dropna(subset=['Date_Ref'])

        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

    # --- MATCHING LOGIC (Same as Picheta) ---
    
    def get_strict_key(row):
        t = str(row.get('Num Ticket', '')).strip().upper()
        b = str(row.get('Num Bon', '')).strip().upper()
        vides = ['ST', 'NAN', '', 'NONE', '0', 'None']
        if t not in vides: return t
        if b not in vides: return b
        return np.nan

    df_ter['K'] = df_ter.apply(get_strict_key, axis=1)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace('NAN', np.nan).replace('', np.nan)

    # 1. Strict Match
    m1 = pd.merge(
        df_ter.dropna(subset=['K']), 
        df_ref.dropna(subset=['K']), 
        on='K', 
        how='outer', 
        indicator=True, 
        suffixes=('_T', '_F')
    )
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'

    matched_ids_t = match1['K'].unique()
    matched_ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(matched_ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(matched_ids_f)].copy()

    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")

        l_ter_valid = l_ter[l_ter['Key_Date'] != "NAN"].copy()
        l_ref_valid = l_ref[l_ref['Key_Date'] != "NAN"].copy()

        if not l_ter_valid.empty and not l_ref_valid.empty:
            m_cross = pd.merge(l_ter_valid, l_ref_valid, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        else:
            m_cross = pd.DataFrame()
        
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta_Poids'] = (p_t - p_f).abs()
            
            candidates = m_cross[m_cross['Delta_Poids'] <= 0.5].copy()
            candidates = candidates.sort_values('Delta_Poids')
            
            if 'Num Bon' in candidates.columns:
                match2 = candidates.drop_duplicates(subset=['Num Bon'], keep='first')
            else:
                match2 = candidates.drop_duplicates(subset=['Key_Date', 'Poids_Terrain'], keep='first')
                
            if not match2.empty:
                match2['Methode'] = '2. Smart Match'
                match2['_merge'] = 'both'
                
                # Cleanup matched
                matched_uids_ter = (match2['Key_Date'].astype(str) + "_" + match2['Poids_Terrain'].astype(str)).tolist()
                l_ter['_UID'] = l_ter['Key_Date'].astype(str) + "_" + l_ter['Poids_Terrain'].astype(str)
                final_t = l_ter[~l_ter['_UID'].isin(matched_uids_ter)].drop(columns=['_UID'])
                
                if 'Num Ticket_F' in match2.columns:
                    matched_tickets = match2['Num Ticket_F'].tolist()
                    final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets)]
                else:
                    final_f = l_ref
            else:
                final_t, final_f = l_ter, l_ref
        else:
            final_t, final_f = l_ter, l_ref
    else:
        final_t, final_f = l_ter, l_ref

    # 3. Flex Match (Date +/- 3 days)
    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'].apply(convertir_date_robuste), errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'].apply(convertir_date_robuste), errors='coerce')
         
         offset_dfs = []
         for offset in range(-3, 4):
             temp = final_t.dropna(subset=['Date_Obj']).copy()
             temp['Join_Date'] = temp['Date_Obj'] + pd.Timedelta(days=offset)
             temp['_Offset'] = offset
             offset_dfs.append(temp)
             
         t_expanded = pd.concat(offset_dfs)
         m_flex = pd.merge(t_expanded, final_f.dropna(subset=['Date_Obj']), left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
         
         if not m_flex.empty:
             m_flex['Delta_Poids'] = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs()
             candidates_3 = m_flex[m_flex['Delta_Poids'] <= 0.5].copy()
             candidates_3 = candidates_3.sort_values(['_Offset', 'Delta_Poids'])
             
             if not candidates_3.empty:
                 if 'Num Bon' in candidates_3.columns:
                     match3 = candidates_3.drop_duplicates(subset=['Num Bon'], keep='first')
                 else:
                     match3 = candidates_3.drop_duplicates(subset=['Date_Ref_T', 'Poids_Terrain'], keep='first')
                 
                 match3['Methode'] = '3. Match Flex Date'
                 match3['_merge'] = 'both'
                 match3['Date_Ref'] = match3['Date_Ref_T']

                 matched_uids_t = (match3['Num Ticket_T'].apply(str) + match3['Poids_Terrain'].apply(str)).tolist()
                 final_t['_UID'] = final_t['Num Ticket'].apply(str) + final_t['Poids_Terrain'].apply(str)
                 
                 final_t = final_t[~final_t['_UID'].isin(matched_uids_t)].drop(columns=['_UID'])
                 # Simplification for final_f exclusion (not perfect but acceptable)
                 
         if 'Date_Obj' in final_t.columns: final_t = final_t.drop(columns=['Date_Obj'])
         if 'Date_Obj' in final_f.columns: final_f = final_f.drop(columns=['Date_Obj'])

    # Final concat
    cols_ter = df_ter.columns
    cols_ref = df_ref.columns
    
    final_orph_t = final_t.rename(columns={c: c + '_T' for c in cols_ter})
    final_orph_f = final_f.rename(columns={c: c + '_F' for c in cols_ref})
    
    final_orph_t['_merge'] = 'left_only'; final_orph_t['Methode'] = 'Non Trouvé'
    final_orph_f['_merge'] = 'right_only'; final_orph_f['Methode'] = 'Non Trouvé'

    final = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True)
    final['Exutoire'] = "PICHETA VALOSEINE DECH TRIEL"
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
        
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str)
    
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    
    # Fill from T/F specific columns if main is 0
    p_ter_t = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_ter_t)
    
    p_fac_f = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_fac_f)

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    
    final['INT Client'] = final.get('Client_T', final.get('Client')).fillna("GPSEO").astype(str)
    final['EXT Client'] = final.get('Client_F').fillna("").astype(str)
    
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    
    def check_mat(row):
        if row['_merge'] != 'both': return "OK" # Or Pb.Ext
        mt = str(row.get('Matiere_T', '')).upper()
        mf = str(row.get('EXT_Matiere', '')).upper()
        if mt == mf or mt in mf or mf in mt: return "OK"
        return "Pb.Mat"
    
    final['Verif_Matiere'] = final.apply(check_mat, axis=1)
    final['Activité'] = resolve_col(final, 'Activité').fillna("DECH")

    def check_client_picheta(row):
        int_c = str(row.get('INT Client', '')).upper().strip()
        ext_c = str(row.get('EXT Client', '')).upper().strip()
    
        if not int_c or not ext_c: return "OK"
        if "TRIEL" in int_c and "TRIEL" in ext_c: return "OK"
        if int_c == ext_c: return "OK"
    
        k1 = normalize_site_key(int_c)
        k2 = normalize_site_key(ext_c)
    
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
    
        s1 = set(k1.split())
        s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        
        return "Pb.Clt"

    final['Verif_Client'] = final.apply(check_client_picheta, axis=1)



    return final


def charger_picheta_smirtom(f, source_name="PICHETA SMIRTOM"):
    try:
        # Heuristic for header
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "n°bon de vidage" in row_str or "num tp manuel" in row_str: idx = i; break
            
        f.seek(0)
        df = pd.read_excel(f, header=idx, dtype=str)
        
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "n°bon de vidage" in cl: cols[c] = "Num Bon"
            elif "tonnages" in cl: cols[c] = "Poids_Terrain"
            elif "date" in cl and "vidage" not in cl: cols[c] = "Date_Ref" # Prefer "Date" over "Date vidage" if both? usually distinct 
            elif "exutoire" in cl: cols[c] = "Exutoire"
            elif "immat" in cl or "camion" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "nature" in cl: cols[c] = "Matiere_T"
            
        df = df.rename(columns=cols)
        
        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
            
        df['Activité'] = source_name
        # [USER REQUEST] Strict parsing
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Picheta Smirtom ({source_name}): {e}")
        return pd.DataFrame()

def process_picheta_smirtom(f_ter, f_fac):
    logger.info("Début traitement PICHETA SMIRTOM")
    
    # 1. Load Terrain
    df_ter = charger_picheta_smirtom(f_ter, "DECH")
    
    if df_ter.empty: return pd.DataFrame()
    
    # 2. Load Invoice
    temp = pd.read_excel(f_fac, header=None, nrows=30)
    idx_inv = 0
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        if "n° document" in row_str and "q liv" in row_str: idx_inv = i; break
        
    f_fac.seek(0)
    df_ref = pd.read_excel(f_fac, header=idx_inv, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° document" in cl: cols_ref[c] = "Num Ticket"
        if "q liv" in cl: cols_ref[c] = "Poids_Facture"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "chantier" in cl: cols_ref[c] = "Client" # Might need cleaning
        if "libellé produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"

    df_ref = df_ref.rename(columns=cols_ref)
    
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')

    if 'TEMP_CodeAdresse' in df_ref.columns:
        df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETTERIE PICHETA SMIRTOM')
    else:
        df_ref['Client'] = "DECHETTERIE PICHETA SMIRTOM"
        
    # Date Repair Invoice
    # [USER REQUEST] Strict parsing
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    # Filter out noise (Section headers in invoice)
    if 'Num Ticket' in df_ref.columns:
         df_ref = df_ref[~df_ref['Num Ticket'].astype(str).str.contains("Libellé interne", na=False)]

    # Cleaning
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
    # --- MATCHING Logic ---
    # 1. Strict (Ticket)
    
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs()
            
            cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first') # Ticket F is reliable
                 
                 match2['Methode'] = '2. Smart Match'
                 match2['_merge'] = 'both'
                 
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str) + "_" + match2['Num Ticket_T'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str) + "_" + l_ter['Num Ticket'].astype(str)
                 
                 uids_done = match2['UID_T'].unique()
                 final_t = l_ter[~l_ter['UID_T'].isin(uids_done)].drop(columns=['UID_T'])
                 if 'UID_T' in match2.columns: match2 = match2.drop(columns=['UID_T'])
                 
                 final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
            else:
                 final_t, final_f = l_ter, l_ref
        else:
            final_t, final_f = l_ter, l_ref
    else:
        final_t, final_f = l_ter, l_ref

    # 3. Flex Match (Date +/- 3 days)
    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'].apply(convertir_date_robuste), errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'].apply(convertir_date_robuste), errors='coerce')
         
         dfs_off = []
         for off in range(-3, 4):
             tmp = final_t.dropna(subset=['Date_Obj']).copy()
             tmp['Join_Date'] = tmp['Date_Obj'] + pd.Timedelta(days=off)
             dfs_off.append(tmp)
         
         t_exp = pd.concat(dfs_off)
         m_flex = pd.merge(t_exp, final_f.dropna(subset=['Date_Obj']), left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
         
         if not m_flex.empty:
             diff = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs()
             cands3 = m_flex[diff <= 0.05].sort_values('Poids_Terrain') # Sort to stabilize
             
             if not cands3.empty:
                 match3 = cands3.drop_duplicates(subset=['Num Ticket_F'], keep='first')
                 match3['Methode'] = '3. Flex Match'
                 match3['_merge'] = 'both'
                 match3['Date_Ref'] = match3['Date_Ref_T']
                 
                 matched_tf = match3['Num Ticket_F'].tolist()
                 # Approximate cleaning for T side
                 match3['UID_T'] = match3['Num Ticket_T'].astype(str) + "_" + match3['Poids_Terrain'].astype(str)
                 final_t['UID_T'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str)
                 uids3 = match3['UID_T'].unique()
                 
                 final_t = final_t[~final_t['UID_T'].isin(uids3)]
                 if 'UID_T' in final_t.columns: final_t = final_t.drop(columns=['UID_T'])
                 if 'UID_T' in match3.columns: match3 = match3.drop(columns=['UID_T'])
                 
                 final_f = final_f[~final_f['Num Ticket'].isin(matched_tf)]
                 
    # Final Concat
    cols_t = df_ter.columns
    cols_f = df_ref.columns
    
    orph_t = final_t.rename(columns={c: c + '_T' for c in cols_t})
    orph_f = final_f.rename(columns={c: c + '_F' for c in cols_f})
    
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    # Debug/Safety : Ensure no duplicate columns before concat
    dfs_to_concat = [match1, match2, match3, orph_t, orph_f]
    cleaned_dfs = [d.loc[:, ~d.columns.duplicated()] for d in dfs_to_concat]
    
    final = pd.concat(cleaned_dfs, ignore_index=True)
    final['Exutoire'] = "PICHETA SMIRTOM"
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
        
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str)
    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str)
    
    # Poids Terrain: if merged, take terrain. 
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    
    final['INT Client'] = final.get('Client_T', final.get('Client')).fillna("SMIRTOM").astype(str)
    final['EXT Client'] = final.get('Client_F').fillna("").astype(str)
    
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Activité'] = resolve_col(final, 'Activité').fillna("DECH")
    def check_client_picheta(row):
        int_c = str(row.get('INT Client', '')).upper().strip()
        ext_c = str(row.get('EXT Client', '')).upper().strip()
    
        if not int_c or not ext_c: return "OK"
        if int_c == ext_c: return "OK"
    
        # Logic similar to Suez
        k1 = normalize_site_key(int_c)
        k2 = normalize_site_key(ext_c)
    
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
    
        s1 = set(k1.split())
        s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        
        return "Pb.Clt"

    final['Verif_Client'] = final.apply(check_client_picheta, axis=1)
    
    return final

def charger_picheta_inoe(f, source_name="PICHETA INOE"):
    try:
        # Heuristic for header
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num tp manuel" in row_str and "num bon" in row_str: idx = i; break
            if "date" in row_str and "exutoire" in row_str: idx = i; break
            
        f.seek(0)
        df = pd.read_excel(f, header=idx, dtype=str)
        
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "num bon" in cl or "n°bon" in cl: cols[c] = "Num Bon"
            elif "quantiteligne" in cl: cols[c] = "Poids_Terrain"
            elif "date" in cl and "vidage" not in cl: cols[c] = "Date_Ref" # Prefer "Date" over "Date vidage" if both? usually distinct 
            elif "exutoire" in cl: cols[c] = "Exutoire"
            elif "immat" in cl or "camion" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "description" in cl or "nature" in cl: cols[c] = "Matiere_T"
            
        df = df.rename(columns=cols)
        
        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
            
        df['Activité'] = source_name
        # [USER REQUEST] Strict parsing
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Picheta Inoe ({source_name}): {e}")
        return pd.DataFrame()

def process_picheta_inoe(f_ctc, f_dech, f_inv):
    logger.info("Début traitement PICHETA INOE")
    
    # 1. Load Terrain
    dfs = []
    if f_ctc: dfs.append(charger_picheta_inoe(f_ctc, "CTC"))
    if f_dech: dfs.append(charger_picheta_inoe(f_dech, "DECH"))
    
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    
    # 2. Load Invoice
    temp = pd.read_excel(f_inv, header=None, nrows=30)
    idx_inv = 0
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        if "n° du bl" in row_str and "quantité" in row_str: idx_inv = i; break
        
    f_inv.seek(0)
    df_ref = pd.read_excel(f_inv, header=idx_inv, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° du bl" in cl: cols_ref[c] = "Num Ticket"
        if "quantité" in cl: cols_ref[c] = "Poids_Facture"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "client" in cl: cols_ref[c] = "TEMP_CodeAdresse" # Use Client as address
        if "produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "site de réception" in cl: cols_ref[c] = "Exutoire_F"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"

    df_ref = df_ref.rename(columns=cols_ref)
    
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')

    if 'TEMP_CodeAdresse' in df_ref.columns:
        df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETTERIE PICHETA INOE')
    else:
        df_ref['Client'] = "DECHETTERIE PICHETA INOE"
        
    # Date Repair Invoice
    # [USER REQUEST] Strict parsing
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    # Cleaning
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
    # --- MATCHING Logic ---
    # 1. Strict (Ticket)
    # Note: Invoice has no Num Bon, so strict match is on Ticket only
    
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs()
            
            cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            # Deduplicate by unique identifying content
            if not cands.empty:
                 # Prefer match with closest weight (already sorted)
                 # We need to pick unique pairs. 
                 # Heuristic: dedupe on Ticket_T then Ticket_F (if exist) or just process sequentially
                 # Ideally use linear assignment but simple greedy drop_dup is consistent with other providers
                 match2 = cands.drop_duplicates(subset=['K_T'], keep='first') # K_T might be NaN or ST, so this is weak
                 # Better: Use available ID or index
                 # If K_T is NaN (ST), fallback to Date+Weight as virtual ID
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first') # Ticket F is reliable
                 
                 match2['Methode'] = '2. Smart Match'
                 match2['_merge'] = 'both'
                 
                 # Cleanup
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 # For terrain, we need to know which rows matched. 
                 # Since we lack a unique ID on Terrain side for 'ST' rows, we rely on the merge index or content
                 # Simpler: Filter out from l_ref only, and let l_ter leftovers flow to Flex? 
                 # Actually we should remove matched from l_ter too.
                 # Let's assume unique combination of Date+Weight+Ticket for safety
                 
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str) + "_" + match2['Num Ticket_T'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str) + "_" + l_ter['Num Ticket'].astype(str)
                 
                 uids_done = match2['UID_T'].unique()
                 final_t = l_ter[~l_ter['UID_T'].isin(uids_done)].drop(columns=['UID_T'])
                 if 'UID_T' in match2.columns: match2 = match2.drop(columns=['UID_T'])
                 
                 final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
            else:
                 final_t, final_f = l_ter, l_ref
        else:
            final_t, final_f = l_ter, l_ref
    else:
        final_t, final_f = l_ter, l_ref

    # 3. Flex Match (Date +/- 3 days)
    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'].apply(convertir_date_robuste), errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'].apply(convertir_date_robuste), errors='coerce')
         
         dfs_off = []
         for off in range(-3, 4):
             tmp = final_t.dropna(subset=['Date_Obj']).copy()
             tmp['Join_Date'] = tmp['Date_Obj'] + pd.Timedelta(days=off)
             dfs_off.append(tmp)
         
         t_exp = pd.concat(dfs_off)
         m_flex = pd.merge(t_exp, final_f.dropna(subset=['Date_Obj']), left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
         
         if not m_flex.empty:
             diff = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs()
             cands3 = m_flex[diff <= 0.05].sort_values('Poids_Terrain') # Sort to stabilize
             
             if not cands3.empty:
                 match3 = cands3.drop_duplicates(subset=['Num Ticket_F'], keep='first')
                 match3['Methode'] = '3. Flex Match'
                 match3['_merge'] = 'both'
                 match3['Date_Ref'] = match3['Date_Ref_T']
                 
                 matched_tf = match3['Num Ticket_F'].tolist()
                 # Approximate cleaning for T side
                 match3['UID_T'] = match3['Num Ticket_T'].astype(str) + "_" + match3['Poids_Terrain'].astype(str)
                 final_t['UID_T'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str)
                 uids3 = match3['UID_T'].unique()
                 
                 final_t = final_t[~final_t['UID_T'].isin(uids3)]
                 if 'UID_T' in final_t.columns: final_t = final_t.drop(columns=['UID_T'])
                 if 'UID_T' in match3.columns: match3 = match3.drop(columns=['UID_T'])
                 
                 # F side
                 # final_f handled implicitly by concat remainder? No, need explicit
                 # final_f = l_ref[~l_ref...] Wait, final_f was derived from l_ref previously
                 final_f = final_f[~final_f['Num Ticket'].isin(matched_tf)]
                 
    # Final Concat
    cols_t = df_ter.columns
    cols_f = df_ref.columns
    
    orph_t = final_t.rename(columns={c: c + '_T' for c in cols_t})
    orph_f = final_f.rename(columns={c: c + '_F' for c in cols_f})
    
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    final = pd.concat([match1, match2, match3, orph_t, orph_f], ignore_index=True)
    final['Exutoire'] = "PICHETA INOE"
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
        
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str)
    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str)
    
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    final['INT Client'] = final.get('Client_T', final.get('Client')).fillna("GPSEO").astype(str)
    final['EXT Client'] = final.get('Client_F').fillna("").astype(str)
    
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    # If explicitly marked as ST in terrain, it might match by Date/Weight but fail strict ticket
    
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Activité'] = resolve_col(final, 'Activité').fillna("DECH")

    def check_client_picheta(row):
        int_c = str(row.get('INT Client', '')).upper().strip()
        ext_c = str(row.get('EXT Client', '')).upper().strip()
    
        if not int_c or not ext_c: return "OK"
        if int_c == ext_c: return "OK"
    
        k1 = normalize_site_key(int_c)
        k2 = normalize_site_key(ext_c)
    
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
    
        s1 = set(k1.split())
        s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        
        return "Pb.Clt"

    final['Verif_Client'] = final.apply(check_client_picheta, axis=1)
    
    return final


def display_results(df):
    if df.empty:
        st.warning("Aucun résultat.")
        return

    def highlight_method(row):
        m = str(row.get('Methode', ''))
        if 'Auto' in m or 'Smart' in m: return ['background-color: #d4edda; color: #155724'] * len(row)
        elif 'Ticket' in m: return [''] * len(row)
        else: return ['background-color: #f8d7da; color: #721c24'] * len(row)

    st.write(f"Résultat : {len(df)} lignes traitées.")
    
    cols_view = ['Date_Ref', 'Date', 'Num Ticket', 'Exutoire', 'Client', 'Methode', 'Verif_Exutoire', 'Poids_Terrain', 'Poids_Facture', 'Ecart', 'INT Client', 'EXT Client', 'Verif_Client']
    cols_view = [c for c in cols_view if c in df.columns]
    
    col_config = {}
    for c in ['Date_Ref', 'Date']:
        if c in df.columns:
            col_config[c] = st.column_config.DateColumn("Date", format="DD/MM/YYYY")
            
    st.dataframe(
        df[cols_view].style.apply(highlight_method, axis=1), 
        use_container_width=True,
        column_config=col_config
    )

def charger_azalys(f, source_name="AZALYS"):
    try:
        # Heuristic for header
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "n°bon de vidage" in row_str or "num tp manuel" in row_str: idx = i; break
            
        f.seek(0)
        df = pd.read_excel(f, header=idx, dtype=str)
        
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "n°bon de vidage" in cl: cols[c] = "Num Bon"
            elif "tonnages" in cl: cols[c] = "Poids_Terrain"
            elif "date" in cl: cols[c] = "Date_Ref"
            elif "exutoire" in cl: cols[c] = "Exutoire"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "nature" in cl: cols[c] = "Matiere_T"
            
        df = df.rename(columns=cols)
        
        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
            
        df['Activité'] = source_name
        
        if 'Date_Ref' in df.columns:
             df['Date_Ref'] = pd.to_datetime(df['Date_Ref'], errors='coerce').dt.date
        
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Azalys ({source_name}): {e}")
        return pd.DataFrame()

def process_azalys(f_ter, f_fac, provider_name):
    logger.info(f"Début traitement {provider_name}")
    
    # 1. Load Terrain
    df_ter = charger_azalys(f_ter, provider_name)
    if df_ter.empty: return pd.DataFrame()
    
    # 2. Load Invoice
    # Invoice header is usually row 0
    df_ref = pd.read_excel(f_fac, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "numéro de ticket" in cl: cols_ref[c] = "Num Ticket"
        if "net" in cl: cols_ref[c] = "Poids_Facture" # In kg usually
        if "date du poids" in cl and "entrée" in cl: cols_ref[c] = "Date_Ref"
        if "libellé tiers" in cl: cols_ref[c] = "Client"
        if "libellé produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "unité" in cl: cols_ref[c] = "Unite"
        if "immat" in cl or "véhicule" in cl: cols_ref[c] = "Immatriculation"

    df_ref = df_ref.rename(columns=cols_ref)
    
    # Poids Facture conversion (kg -> T)
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
        # Check unit if available, otherwise assume > 1000 means kg
        df_ref["Poids_Facture"] = df_ref["Poids_Facture"] / 1000.0
        
    if 'Date_Ref' in df_ref.columns:
         df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date

    # Cleaning keys
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
    # --- MATCHING Logic ---
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs()
            
            cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first')
                 match2['Methode'] = '2. Smart Match'
                 match2['_merge'] = 'both'
                 
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 # Cleanup leftovers
                 l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                 
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str)
                 uids = match2['UID_T'].unique()
                 l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T'])
                 match2 = match2.drop(columns=['UID_T'])

    # Final Concat
    cols_t = df_ter.columns
    cols_f = df_ref.columns
    
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f})
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)

    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str)
    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    final['INT Client'] = final.get('Client_T', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    final['EXT Client'] = final.get('Client_F', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final)))
    c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final)))
    c_ch_f = final.get('Chauffeur_F', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f).astype(str).replace(['nan', 'NAN', 'None'], '')

    c_im = final.get('Immatriculation', pd.Series([np.nan]*len(final)))
    c_im_t = final.get('Immatriculation_T', pd.Series([np.nan]*len(final)))
    c_im_f = final.get('Immatriculation_F', pd.Series([np.nan]*len(final)))
    final['Immatriculation'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace(['nan', 'NAN', 'None'], '')
    
    final['Activité'] = provider_name
    final['Exutoire'] = provider_name
    
    # Verifications
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"

    def check_cl(row):
        i = str(row.get('INT Client','')).upper().strip()
        e = str(row.get('EXT Client','')).upper().strip()
        if not i or not e: return "OK"
        if i == e: return "OK"
        if normalize_site_key(i) == normalize_site_key(e): return "OK"
        
        # Exception requested: AZALYS SOTREMA if INT Client != TRIEL => OK
        if provider_name == "AZALYS SOTREMA" and "TRIEL" not in i: return "OK"
        
        # Intersection logic
        k1 = normalize_site_key(i)
        k2 = normalize_site_key(e)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        
        s1 = set(k1.split())
        s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        
        return "Pb.Clt"
        
    final['Verif_Client'] = final.apply(check_cl, axis=1)
    final['Activité'] = provider_name
    
    return final



def charger_valoseine_enc(f):
    try:
        # Heuristic for detecting the header row
        # Based on inspection, data starts after a header that might contain "Date" or "Heure"
        # But inspection showed data starting around line 12 with columns like "CU GPSO" etc.
        # Let's try to find a row that looks like a header or just skip a fixed number if consistent.
        # Inspection showed: 
        # 12 2026-01-13 ...
        # It seems there is no clear header row in the first few lines of data shown in inspection (it was data directly).
        # Let's read with header=None and look for the structure.
        
        df = pd.read_excel(f, header=None)
        
        # Heuristic: find row where column 0 is a date or looks like data
        # From inspection: Col 0 is Date, Col 2 is Client, Col 6 is Ticket (PRC...), Col 7 is Ticket (PRC...), Col 9 is Weight.
        # Wait, inspection output: 
        # 12 2026-01-13 ... Col 2: CU GPSO ... Col 6: PRC591783 ... Col 7: SITA ... Col 8: Encombrants ... Col 9: 0.42
        # Actually in the inspection print:
        # 12 2026-01-13 ... 
        # The indices in `print(df.to_string())` are the pandas indices, but the columns are 0, 1, 2...
        # Col 0: Date
        # Col 1: CU GPSO (looks like a grouping)
        # Col 2: AIDE RATTRAPAGE (Client?)
        # Col 3: HAOUMAL (Chauffeur?)
        # Col 4: CW-373-EV
        # Col 5: 01264279
        # Col 6: PRC591783 (Ticket!)
        # Col 7: SITA (Compte CU)
        # Col 8: Encombrants CU GPSEO
        # Col 9: 0.42 (Poids)
        
        # So:
        # Ticket = Col 6
        # Poids = Col 9
        # Client = Col 2
        # Date = Col 0
        
        # We need to filter out rows that don't match this structure (e.g. headers, empty lines).
        # Valid row: Col 6 starts with "PRC" or "TM".
        
        data = []
        for i, row in df.iterrows():
            # Check if likely data row
            # Check ticket col (6)
            if len(row) > 6:
                ticket_val = str(row[6]).strip().upper()
                if (ticket_val.startswith("PRC") or ticket_val.startswith("TM")) and len(ticket_val) > 4:
                    # It's a data row
                    r_date = row[0]
                    r_client = row[2]
                    r_poids = row[9] if len(row) > 9 else 0
                    
                    data.append({
                        "Date_Ref": r_date,
                        "Client": r_client,
                        "Num Ticket": ticket_val,
                        "Poids_Terrain": r_poids,
                        "Num Bon": str(row[5]).replace(".0","") if len(row) > 5 else "", 
                        "Matiere_T": row[8] if len(row) > 8 else "",
                        "Chauffeur": str(row[3]).replace("nan", "") if len(row) > 3 else "",
                        "Immat": str(row[4]).replace("nan", "") if len(row) > 4 else ""
                    })
                
        new_df = pd.DataFrame(data)
        if "Poids_Terrain" in new_df.columns:
            new_df["Poids_Terrain"] = pd.to_numeric(new_df["Poids_Terrain"], errors='coerce')
        
        new_df['Activité'] = "ENCOMBRANTS" # Or "ENC"
        
        if 'Date_Ref' in new_df.columns:
             new_df['Date_Ref'] = pd.to_datetime(new_df['Date_Ref'], errors='coerce').dt.date

        return new_df
        
    except Exception as e:
        logger.error(f"Erreur chargement Valoseine ENC: {e}")
        return pd.DataFrame()

def process_valoseine_enc(f_ter, f_fac):
    logger.info("Début traitement VALOSEINE ENC GPSEO")
    
    # 1. Load Terrain
    df_ter = charger_valoseine_enc(f_ter)
    if df_ter.empty: return pd.DataFrame()
    
    # 2. Load Invoice
    # Invoice header is standard row 0
    df_ref = pd.read_excel(f_fac, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° bon de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "quantité nette" in cl: cols_ref[c] = "Poids_Facture" # In kg
        if "date du bon" in cl: cols_ref[c] = "Date_Ref"
        if "nom recherche producteur" in cl: cols_ref[c] = "Producteur" # Used for filtering
        if "ville de l'adresse de service" in cl: cols_ref[c] = "Client" # Real EXT Client
        if "description déchet" in cl: cols_ref[c] = "EXT_Matiere"
        if "nom du transporteur" in cl: cols_ref[c] = "Transporteur"
        if "immat" in cl or "véhicule" in cl: cols_ref[c] = "Immat"

    df_ref = df_ref.rename(columns=cols_ref)
    
    # Filter requested by user: Producteur=VALOOU47 AND Transporteur=SOTREMA
    if 'Producteur' in df_ref.columns and 'Transporteur' in df_ref.columns:
        df_ref = df_ref[
            (df_ref['Producteur'].astype(str).str.strip().str.upper() == 'VALOOU47') & 
            (df_ref['Transporteur'].astype(str).str.strip().str.upper() == 'SOTREMA')
        ]
    
    # Poids Facture conversion (kg -> T)
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
        df_ref["Poids_Facture"] = df_ref["Poids_Facture"] / 1000.0
        
    if 'Date_Ref' in df_ref.columns:
         df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date

    # Cleaning keys
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

    # --- MATCHING Logic (Reused from Azalys/Picheta) ---
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs()
            
            cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first')
                 match2['Methode'] = '2. Smart Match'
                 match2['_merge'] = 'both'
                 
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 # Cleanup
                 l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                 
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str)
                 uids = match2['UID_T'].unique()
                 l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T'])
                 match2 = match2.drop(columns=['UID_T'])

    # Final Concat
    cols_t = df_ter.columns
    cols_f = df_ref.columns
    
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f})
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)

    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    final['INT Client'] = final.get('Client_T', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    final['EXT Client'] = final.get('Client_F', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    
    # Coalesce Chauffeur/Immat (might be 'Chauffeur' or 'Chauffeur_T' depending on merge)
    # If the column was in df_ter but not df_ref, match1 has 'Chauffeur'. orph_t has 'Chauffeur_T'.
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final)))
    c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final)))
    c_ch_f = final.get('Chauffeur_F', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f).astype(str).replace('nan', '')

    c_im = final.get('Immat', pd.Series([np.nan]*len(final)))
    c_im_t = final.get('Immat_T', pd.Series([np.nan]*len(final)))
    c_im_f = final.get('Immat_F', pd.Series([np.nan]*len(final)))
    final['Immat'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace('nan', '')
    
    final['Activité'] = "ENCOMBRANTS"
    final['Exutoire'] = "VALOSEINE ENC GPSEO"
    
    # Verifications
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    # If explicitly marked as ST, it might be OK
    
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"

    def check_cl(row):
        i = str(row.get('INT Client','')).upper().strip()
        e = str(row.get('EXT Client','')).upper().strip()
        if not i or not e: return "OK"
        if i == e: return "OK"
        if normalize_site_key(i) == normalize_site_key(e): return "OK"
        
        k1 = normalize_site_key(i)
        k2 = normalize_site_key(e)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split())
        s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        
        return "Pb.Clt"
        
    final['Verif_Client'] = final.apply(check_cl, axis=1)
    
    return final



def charger_vert_compost_smirtom(file_path):
    try:
        # Based on inspection: data starts around line 12. No standard header.
        # Col 2: Ticket (idx 2)
        # Col 4: Immat (idx 4)
        # Col 5: Transporteur (idx 5)
        # Col 7: Site/Client (idx 7)
        # Col 9: Poids (idx 9) - seems to be in kg (e.g. 2720)
        
        df = pd.read_excel(file_path, header=None)
        data = []
        
        for i, row in df.iterrows():
            if len(row) > 9:
                # Based on debug_columns.py:
                # Col 0: Date
                # Col 1: SMIRTOM DU VEXIN
                # Col 2: DECHETTERIE MARINES (Client)
                # Col 3: Chauffeur
                # Col 4: Immat
                # Col 5: Num Bon
                # Col 6: Ticket (e.g. 1146096)
                # Col 7: VERT COMPOST
                # Col 8: Matiere
                # Col 9: Poids (Tonnes, e.g. 3.3)

                ticket_val = str(row[6]).strip()
                
                # Check if it looks like a ticket (numeric, length > 4)
                if ticket_val.isdigit() and len(ticket_val) > 4:
                    r_date = row[0]
                    
                    data.append({
                        "Date_Ref": r_date,
                        "Num Ticket": ticket_val,
                        "Poids_Terrain": row[9], # Tonnes
                        "Client": str(row[2]).strip() if len(row) > 2 else "",
                        "Immat": str(row[4]).strip() if len(row) > 4 else "",
                        "Num Bon": str(row[5]).strip().replace(".0","") if len(row) > 5 else "",
                        "Chauffeur": str(row[3]).strip() if len(row) > 3 else "",
                        "Matiere_T": str(row[8]).strip() if len(row) > 8 else ""
                    })
                    
        new_df = pd.DataFrame(data)
        
        # Unit conversion: Seems to be already in Tonnes (e.g. 3.3), so NO division.
        if "Poids_Terrain" in new_df.columns:
            new_df["Poids_Terrain"] = pd.to_numeric(new_df["Poids_Terrain"], errors='coerce')
            
        if 'Date_Ref' in new_df.columns:
             new_df['Date_Ref'] = pd.to_datetime(new_df['Date_Ref'], errors='coerce').dt.date
             
        new_df['Activité'] = "DECHETS VEGETAUX"
        
        return new_df
    except Exception as e:
        logger.error(f"Erreur chargement Vert Compost Smirtom: {e}")
        return pd.DataFrame()


def process_vert_compost_smirtom(f_ter, f_fac):
    logger.info("Début traitement VERT COMPOST SMIRTOM")
    
    # 1. Load Terrain
    df_ter = charger_vert_compost_smirtom(f_ter)
    if df_ter.empty: return pd.DataFrame()
    
    # 2. Load Invoice
    # Inspection shows headers: Numéro de pesée, Quantité, Immatriculation
    df_ref = pd.read_excel(f_fac, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "ticket n°" in cl or "numéro de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "net (kg)" in cl: 
            cols_ref[c] = "Poids_Facture" 
            # Needs conversion kg -> T later
        elif "quantité" in cl and "net" not in cl: 
            cols_ref[c] = "Poids_Facture" # Fallback
            
        if "matricule" in cl or "immatriculation" in cl: cols_ref[c] = "Immat"
        if "date" in cl and "sortie" not in cl: cols_ref[c] = "Date_Ref"
        if "produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "client" in cl: cols_ref[c] = "EXT Client"

    df_ref = df_ref.rename(columns=cols_ref)
    
    # Weigh conversion
    if "Poids_Facture" in df_ref.columns:
        # Check if source was Net (kg) => Divide by 1000
        # If column name was originally "Net (kg)", it's kg.
        # But we renamed it. 
        # Let's check values? Or assume new mapping implies kg if "Net (kg)" matched.
        # Since we just renamed, we can check if we should iterate again?
        # Simpler: convert all to numeric first.
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
        
        # If header was Net (kg), we should divide.
        # How to know which header matched?
        # Let's look at df_ref BEFORE rename? No, it's done.
        # But we can inspect logic:
        # If the values are large (> 100), likely kg.
        # If values < 50, likely Tonnes.
        # Heuristic: if mean > 100, divide by 1000.
        mean_val = df_ref["Poids_Facture"].mean()
        if mean_val > 50:
             df_ref["Poids_Facture"] = df_ref["Poids_Facture"] / 1000.0
        
    if 'Date_Ref' in df_ref.columns:
         df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date

    # Cleaning keys
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        # Filter empty tickets (likely totals)
        df_ref = df_ref[df_ref['Num Ticket'] != '']

    # --- MATCHING Logic ---
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs()
            
            # Tolerance 0.05 T
            cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first')
                 match2['Methode'] = '2. Smart Match'
                 match2['_merge'] = 'both'
                 
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 # Cleanup
                 l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                 
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str)
                 uids = match2['UID_T'].unique()
                 l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T'])
                 match2 = match2.drop(columns=['UID_T'])

    # Final Concat
    cols_t = df_ter.columns
    cols_f = df_ref.columns
    
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f})
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)

    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)

    # Consolidation
    # INT Client from Terrain 'Client'
    # match1 has 'Client'. orph_t has 'Client_T'.
    # We need to coalesce.
    c_int = final.get('Client', pd.Series([np.nan]*len(final)))
    c_int_t = final.get('Client_T', pd.Series([np.nan]*len(final)))
    final['INT Client'] = c_int.fillna(c_int_t).astype(str).replace('nan', '')

    # EXT Client from Invoice 'EXT Client'
    # match1 has 'EXT Client'. orph_f has 'EXT Client_F'.
    c_ext = final.get('EXT Client', pd.Series([np.nan]*len(final)))
    c_ext_f = final.get('EXT Client_F', pd.Series([np.nan]*len(final)))
    final['EXT Client'] = c_ext.fillna(c_ext_f).astype(str).replace('nan', '')

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    
    # Coalesce Immat
    c_im = final.get('Immat', pd.Series([np.nan]*len(final)))
    c_im_t = final.get('Immat_T', pd.Series([np.nan]*len(final)))
    c_im_f = final.get('Immat_F', pd.Series([np.nan]*len(final)))
    final['Immat'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace('nan', '')
    
    c_nb = final.get('Num Bon', pd.Series([np.nan]*len(final)))
    c_nb_t = final.get('Num Bon_T', pd.Series([np.nan]*len(final)))
    final['Num Bon'] = c_nb.fillna(c_nb_t).astype(str).replace('nan', '')

    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final)))
    c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).astype(str).replace('nan', '')
    
    final['Activité'] = "DECHETS VEGETAUX"
    final['Exutoire'] = "VERT COMPOST SMIRTOM"
    
    # Verifications
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Verif_Client'] = "OK" # Simplified for now as Client matching might be loose

    return final



def charger_satel_smirtom_enc(file_path):
    try:
        # Based on inspection: No header. Data starts row 0.
        # Col 0: Date (2026-01-02)
        # Col 1: Chauffeur (AOUATE)
        # Col 2: Immat (FG-254-YJ)
        # Col 3: Ticket (01261546)
        # Col 4: Matiere (Encombrants)
        # Col 5: Transporteur (SATEL...)
        # Col 6: Client (DECHETTERIE MAGNY...)
        # Col 8: Poids (3.9) -> Seems to be Tonnes (Invoice matches 3.9)
        
        df = pd.read_excel(file_path, header=None)
        data = []
        
        for i, row in df.iterrows():
            # Check for valid date/weight row
            if len(row) > 8:
                # Basic validation: Col 8 should be numeric
                try:
                    p = float(row[8])
                except:
                    continue # Skip invalid rows
                
                r_date = row[0]
                
                data.append({
                    "Date_Ref": r_date,
                    "Num Ticket": str(row[3]).strip(),
                    "Poids_Terrain": p, # Tonnes
                    "Client": str(row[6]).strip() if len(row) > 6 else "",
                    "Immat": str(row[2]).strip() if len(row) > 2 else "",
                    "Chauffeur": str(row[1]).strip() if len(row) > 1 else "",
                    "Matiere_T": str(row[4]).strip() if len(row) > 4 else "",
                    "Transporteur": str(row[5]).strip() if len(row) > 5 else ""
                })
                    
        new_df = pd.DataFrame(data)
        
        # Unit conversion: Already Tonnes.
        if "Poids_Terrain" in new_df.columns:
            new_df["Poids_Terrain"] = pd.to_numeric(new_df["Poids_Terrain"], errors='coerce')
            
        if 'Date_Ref' in new_df.columns:
             new_df['Date_Ref'] = pd.to_datetime(new_df['Date_Ref'], errors='coerce').dt.date
             
        new_df['Activité'] = "ENCOMBRANTS"
        
        return new_df
    except Exception as e:
        logger.error(f"Erreur chargement SATEL SMIRTOM ENC: {e}")
        return pd.DataFrame()


def process_satel_smirtom_enc(f_ter, f_fac):
    logger.info("Début traitement SATEL SMIRTOM ENC")
    
    # 1. Load Terrain
    df_ter = charger_satel_smirtom_enc(f_ter)
    if df_ter.empty: return pd.DataFrame()
    
    # 2. Load Invoice
    # Robust header detection
    df_ref_raw = pd.read_excel(f_fac, header=None, dtype=str)
    
    header_row_idx = None
    for i, row in df_ref_raw.iterrows():
        r_str = row.astype(str).str.lower().tolist()
        if any("num bon" in s for s in r_str) and any("nomclient" in s for s in r_str):
            header_row_idx = i
            break
            
    if header_row_idx is not None:
        # Reload or slice
        df_ref = df_ref_raw.iloc[header_row_idx+1:].copy()
        df_ref.columns = df_ref_raw.iloc[header_row_idx]
        df_ref.columns = df_ref.columns.astype(str) # Force string headers
        
        # Dedup columns (e.g. Code, Code)
        new_cols = []
        seen = {}
        for c in df_ref.columns:
            c_str = str(c).strip()
            if c_str in seen:
                seen[c_str] += 1
                new_cols.append(f"{c_str}.{seen[c_str]}")
            else:
                seen[c_str] = 0
                new_cols.append(c_str)
        df_ref.columns = new_cols

    else:
        # Fallback or error
        logger.warning("Header not found for SATEL Invoice, using default/heuristic?")
        df_ref = df_ref_raw # Likely fail later but better than crash here
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "num bon" in cl: cols_ref[c] = "Num Ticket" # Sotrema ID
        if "quantiteligne" in cl: cols_ref[c] = "Poids_Facture"
        if "immatriculation" in cl: cols_ref[c] = "Immat"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "nomclient" in cl: cols_ref[c] = "EXT Client"
        
        # Mapping Description to EXT_Matiere
        # Ignore Code/Code.1 to avoid duplicates (Use Description for Matiere)
        if "description" in cl: cols_ref[c] = "EXT_Matiere"

    df_ref = df_ref.rename(columns=cols_ref)
    
    # Weigh conversion: Invoice is likely Tonnes (matches 3.9)
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
        
    if 'Date_Ref' in df_ref.columns:
         df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date

    # Cleaning keys
    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        # Filter empty
        df_ref = df_ref[df_ref['Num Ticket'] != '']

    # --- MATCHING Logic ---
    # Ticket numbers map: SATEL (e.g. 01261546) vs SOTREMA (e.g. 01260290)
    # They look different. But let's try exact match first just in case.
    
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    # 2. Smart Match (Date + Weight)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs()
            
            # Tolerance 0.05 T
            cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first')
                 match2['Methode'] = '2. Smart Match'
                 match2['_merge'] = 'both'
                 
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 # Cleanup
                 l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                 
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str)
                 uids = match2['UID_T'].unique()
                 l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T'])
                 match2 = match2.drop(columns=['UID_T'])

    # Final Concat
    cols_t = df_ter.columns
    cols_f = df_ref.columns
    
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f})
    orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    
    # Consolidation
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)

    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)

    # Consolidation
    # INT Client from Terrain 'Client'
    c_int = final.get('Client', pd.Series([np.nan]*len(final)))
    c_int_t = final.get('Client_T', pd.Series([np.nan]*len(final)))
    final['INT Client'] = c_int.fillna(c_int_t).astype(str).replace('nan', '')

    # EXT Client from Invoice 'EXT Client'
    c_ext = final.get('EXT Client', pd.Series([np.nan]*len(final)))
    c_ext_f = final.get('EXT Client_F', pd.Series([np.nan]*len(final)))
    final['EXT Client'] = c_ext.fillna(c_ext_f).astype(str).replace('nan', '')

    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    
    # Coalesce Immat
    c_im = final.get('Immat', pd.Series([np.nan]*len(final)))
    c_im_t = final.get('Immat_T', pd.Series([np.nan]*len(final)))
    c_im_f = final.get('Immat_F', pd.Series([np.nan]*len(final)))
    final['Immat'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace('nan', '')
    
    final['Chauffeur'] = final.get('Chauffeur_T', '').astype(str).replace('nan', '')
    
    final['Activité'] = "ENCOMBRANTS"
    final['Exutoire'] = "SATEL SMIRTOM ENC"
    
    # Verifications
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Verif_Client'] = "OK" 

    return final


def interface_admin():
    st.header(f"🛠️ Gestion BDD (Connecté en tant que : {st.session_state['username']})")
    engine = get_db_engine()
    if not engine: return
    
    check_and_migrate_db(engine)

    col_mode, col_search, col_limit = st.columns([1, 2, 1])
    with col_mode:
        voir_archives = st.checkbox("Voir les lignes archivées 🗑️", value=False)
    with col_limit:
        limit = st.number_input("Lignes", 10, 1000, 50)
    with col_search:
        search = st.text_input("Recherche (Ticket, Bon, Client...)")

    status_bool = not voir_archives
    if search:
        search_pattern = f"%{search}%"
        query = text(f"""
            SELECT * FROM {TABLE_NAME} 
            WHERE "isActive" = :status 
            AND (
                "Num Ticket" ILIKE :s OR 
                "Client" ILIKE :s OR 
                "Num Bon" ILIKE :s OR 
                "Exutoire" ILIKE :s
            )
            ORDER BY id DESC LIMIT :limit
        """)
        params = {"status": status_bool, "s": search_pattern, "limit": limit}
    else:
        query = text(f"SELECT * FROM {TABLE_NAME} WHERE \"isActive\" = :status ORDER BY id DESC LIMIT :limit")
        params = {"status": status_bool, "limit": limit}
    
    try:
        df = pd.read_sql(query, engine, params=params)
        config = {
            "id": st.column_config.NumberColumn(disabled=True),
            "isActive": st.column_config.CheckboxColumn(disabled=False, label="Actif"),
            "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Motif": st.column_config.TextColumn(label="Motif Action"),
        }
        st.caption(f"Affichage des lignes {'ARCHIVÉES' if voir_archives else 'ACTIVES'}")
        edited_df = st.data_editor(df, num_rows="dynamic", key="editor", column_config=config, use_container_width=True)

        if st.button("💾 Sauvegarder les modifications", type="primary"):
            with engine.connect() as conn:
                trans = conn.begin()
                try:
                    ids_apres = set(edited_df['id'].dropna())
                    rows_upd = edited_df[edited_df['id'].isin(ids_apres)]
                    for i, row in rows_upd.iterrows():
                        raw_params = {k: (None if pd.isna(v) else v) for k, v in row.items()}
                        if raw_params.get('Date'): raw_params['Date'] = pd.to_datetime(raw_params['Date'])
                        raw_params['Dernier_Utilisateur'] = st.session_state["username"]
                        safe_params = {}
                        set_parts = []
                        for k, v in raw_params.items():
                            if k == 'id': continue
                            clean_key = k.replace(" ", "_").replace(".", "").replace("-", "")
                            safe_params[clean_key] = v
                            set_parts.append(f'"{k}" = :{clean_key}')
                        safe_params['id_row'] = raw_params['id']
                        if set_parts:
                            set_clause = ", ".join(set_parts)
                            stmt = text(f"UPDATE {TABLE_NAME} SET {set_clause} WHERE id = :id_row")
                            conn.execute(stmt, safe_params)
                    trans.commit()
                    st.success("Modifications enregistrées avec traçage utilisateur.")
                    st.rerun()
                except Exception as e:
                    trans.rollback()
                    logger.error(f"Erreur SQL Save Admin: {e}", exc_info=True)
                    st.error(f"Erreur SQL : {str(e)}")

    except Exception as e:
        logger.error(f"Erreur SQL Fetch Admin: {e}")
        st.error(f"Erreur SQL : {e}")

    st.divider()
    action_label = "♻️ RESTAURER" if voir_archives else "🗑️ ARCHIVER"
    st.subheader(f"Action sur ID : {action_label}")
    c_id, c_motif, c_btn = st.columns([1, 2, 1])
    target_id = c_id.number_input("ID cible", min_value=0, step=1)
    motif_action = c_motif.text_input("Motif de l'action", placeholder="Ex: Doublon, Erreur pesée...")

    if c_btn.button(f"{action_label} la ligne"):
        if target_id > 0:
            new_status = voir_archives # if was archived, set to TRUE (restored)
            with engine.connect() as conn:
                stmt = text(f"UPDATE {TABLE_NAME} SET \"isActive\" = :status, \"Motif\" = :motif, \"Dernier_Utilisateur\" = :user WHERE id = :id")
                res = conn.execute(stmt, {"id": target_id, "motif": motif_action, "user": st.session_state["username"], "status": new_status})
                conn.commit()
                if res.rowcount > 0:
                    st.success(f"Ligne {target_id} {'restaurée' if voir_archives else 'archivée'} !")
                    st.rerun()
                else:
                    st.warning("ID introuvable.")

    st.divider()
    st.subheader("📦 Archivage Périodique")
    
    with st.expander("Archivage par Critères (Exutoire / Période)"):
        c_exu_del, c_dates_del = st.columns(2)
        
        exu_del = c_exu_del.selectbox("Exutoire concerné", ["Selectionner..."] + ["DUPILLE", "PICHETA GPSEO", "VALENE", "SUEZ"])
        dates_del = c_dates_del.date_input("Période cible", [])
        
        motif_del = st.text_input("Motif de l'opération", "Nettoyage périodique")
        
        if st.button("Exécuter l'archivage", type="primary"):
            if exu_del == "Selectionner..." or len(dates_del) != 2:
                st.error("Veuillez sélectionner un exutoire et une période valide (Début - Fin).")
            else:
                d_start, d_end = dates_del
                confirm_msg = f"Êtes-vous sûr de vouloir archiver les données {exu_del} du {d_start} au {d_end} ?"
                
                with engine.connect() as conn:
                    # Count before delete
                    stmt_count = text(f"""
                        SELECT COUNT(*) FROM {TABLE_NAME} 
                        WHERE "Exutoire" = :exutoire 
                        AND "Date" >= :d_start AND "Date" <= :d_end
                        AND "isActive" = TRUE
                    """)
                    count = conn.execute(stmt_count, {"exutoire": exu_del, "d_start": d_start, "d_end": d_end}).scalar()
                    
                    if count == 0:
                        st.warning("Aucune donnée active correspondante trouvée.")
                    else:
                        stmt_upd = text(f"""
                            UPDATE {TABLE_NAME} 
                            SET "isActive" = FALSE, "Motif" = :motif, "Dernier_Utilisateur" = :user 
                            WHERE "Exutoire" = :exutoire 
                            AND "Date" >= :d_start AND "Date" <= :d_end
                        """)
                        conn.execute(stmt_upd, {
                            "motif": motif_del, 
                            "user": st.session_state["username"],
                            "exutoire": exu_del,
                            "d_start": d_start,
                            "d_end": d_end
                        })
                        conn.commit()
                        st.success(f"✅ {count} lignes archivées avec succès.")
                        st.rerun()

    if st.session_state.get("username") == "admin":
        st.divider()
        st.subheader("👤 Création d'un Nouvel Utilisateur")
        with st.form("form_new_user"):
            c1, c2 = st.columns(2)
            new_login = c1.text_input("Identifiant (Login)", placeholder="ex: jdupont")
            new_pass = c2.text_input("Mot de passe", type="password")
            
            submit_user = st.form_submit_button("➕ Créer l'utilisateur", type="primary")
            
            if submit_user:
                if not new_login or not new_pass:
                    st.error("L'identifiant et le mot de passe sont obligatoires.")
                else:
                    new_login = new_login.strip()
                    try:
                        # 1. Hacher le mot de passe
                        hashed_pw = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        
                        # 2. Lire le dict actuel depuis la variable d'env
                        env_users_str = os.getenv("APP_USERS", "{}")
                        users_dict = json.loads(env_users_str)
                        
                        if new_login in users_dict:
                            st.warning(f"L'utilisateur '{new_login}' existe déjà. Son mot de passe va être mis à jour.")
                        
                        # 3. Mettre à jour le dictionnaire
                        users_dict[new_login] = hashed_pw
                        new_env_users_str = json.dumps(users_dict)
                        
                        # 4. Écrire dans le fichier .env
                        env_path = ".env"
                        if os.path.exists(env_path):
                            with open(env_path, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                            
                            with open(env_path, "w", encoding="utf-8") as f:
                                for line in lines:
                                    if line.startswith("APP_USERS="):
                                        f.write(f"APP_USERS={new_env_users_str}\n")
                                    else:
                                        f.write(line)
                            
                            # 5. Mettre à jour la variable d'environnement courante pour prise en compte immédiate
                            os.environ["APP_USERS"] = new_env_users_str
                            
                            st.success(f"Utilisateur '{new_login}' créé/modifié avec succès !")
                        else:
                            st.error("Le fichier .env est introuvable à la racine du projet.")
                            
                    except Exception as e:
                        logger.error(f"Erreur création utilisateur : {e}")
                        st.error(f"Une erreur est survenue : {e}")

def interface_dashboard():
    st.markdown("""
        <style>
        .header-sotrema {
            background-color: #4CAF50;
            padding: 10px;
            border-radius: 5px;
            color: white;
            text-align: center;
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 15px;
        }
        div[data-testid="stDataFrame"] { font-size: 12px; }
        </style>
        <div class="header-sotrema">SUIVI OPÉRATIONNEL DES FLUX DÉCHETS</div>
    """, unsafe_allow_html=True)

    engine = get_db_engine()
    if not engine: return

    query = f"SELECT * FROM {TABLE_NAME} WHERE \"isActive\" = TRUE ORDER BY \"Date\" DESC"
    df = pd.read_sql(query, engine)

    if not df.empty:
        mask_trash = (df['Date'].isna()) & (df['Num Ticket'].isna() | (df['Num Ticket'] == '') | (df['Num Ticket'] == 'None'))
        df = df[~mask_trash]
    
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'])
    for c in ['Poids_Terrain', 'Poids_Facture', 'Ecart']: 
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    for c in ['Num Ticket', 'Num Bon']:
        if c in df.columns: df[c] = df[c].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    for c in ['Validation_Tonnes', 'Validation_Client', 'Validation_Matiere', 'Validation_Exutoire']:
        if c in df.columns:
            df[c] = df[c].fillna(False).infer_objects(copy=False)
        else:
            df[c] = False

    st.sidebar.divider()
    st.sidebar.subheader("📅 Période")
    min_date = df['Date'].min().date() if not df['Date'].isna().all() else datetime.date.today()
    max_date = df['Date'].max().date() if not df['Date'].isna().all() else datetime.date.today()
    
    if "p_date_range" not in st.session_state:
        st.session_state["p_date_range"] = [min_date, max_date]

    def sync_date():
        st.session_state["p_date_range"] = st.session_state["w_date_range"]

    date_range = st.sidebar.date_input(
        "Filtrer par date", 
        value=st.session_state["p_date_range"], 
        key="w_date_range",
        on_change=sync_date
    )

    df_filtered_date = df.copy()
    if len(date_range) == 2:
        d_start, d_end = date_range
        mask_date = (df['Date'].dt.date >= d_start) & (df['Date'].dt.date <= d_end)
        mask_nat = df['Date'].isna()
        df_filtered_date = df[mask_date | mask_nat]

    df_global_opts = df.copy()

    defaults = {
        "p_exutoire": [],
        "p_client": [],
        "p_matiere": [],
        "p_activite": [],
        "p_search_ticket": "",
        "p_search_bon": ""
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

    def sync_exutoire(): st.session_state["p_exutoire"] = st.session_state["w_exutoire"]
    def sync_client(): st.session_state["p_client"] = st.session_state["w_client"]
    def sync_matiere(): st.session_state["p_matiere"] = st.session_state["w_matiere"]
    def sync_activite(): st.session_state["p_activite"] = st.session_state["w_activite"]
    def sync_ticket(): st.session_state["p_search_ticket"] = st.session_state["w_search_ticket"]
    def sync_bon(): st.session_state["p_search_bon"] = st.session_state["w_search_bon"]

    def reset_filters():
        for k in defaults.keys():
            st.session_state[k] = defaults[k]
        st.session_state["w_exutoire"] = []
        st.session_state["w_client"] = []
        st.session_state["w_matiere"] = []
        st.session_state["w_activite"] = []
        st.session_state["w_search_ticket"] = ""
        st.session_state["w_search_bon"] = ""

    with st.expander("🔎 Filtres", expanded=True):
        st.button("🗑️ Effacer les filtres", on_click=reset_filters)

        c_exu, c_tick, c_bon = st.columns(3)
        
        with c_exu:
            exutoires = ["Tous"] + sorted(df_global_opts['Exutoire'].dropna().unique().tolist())
            # Sanitize default
            valid_defaults = [x for x in st.session_state["p_exutoire"] if x in exutoires]
            st.session_state["p_exutoire"] = valid_defaults
            choix_exutoire = st.multiselect("1. Exutoire", exutoires, placeholder="Choisir...", key="w_exutoire", default=st.session_state["p_exutoire"], on_change=sync_exutoire)

        # Création d'un dataset filtré "Dynamique" pour les autres dropdowns
        # Cela permet d'avoir des listes de clients/matières cohérentes avec l'exutoire choisi
        df_opts_dynamic = df_global_opts.copy()
        if choix_exutoire and "Tous" not in choix_exutoire:
            df_opts_dynamic = df_opts_dynamic[df_opts_dynamic['Exutoire'].isin(choix_exutoire)]

        with c_tick: search_ticket = st.text_input("Num Ticket", key="w_search_ticket", value=st.session_state["p_search_ticket"], on_change=sync_ticket)
        with c_bon: search_bon = st.text_input("Num Bon", key="w_search_bon", value=st.session_state["p_search_bon"], on_change=sync_bon)

        c_cli, c_mat, c_act = st.columns(3)
        
        with c_cli:
            clients_dispo = ["Tous"] + sorted(df_opts_dynamic['INT Client'].astype(str).unique().tolist())
            valid_defaults_cli = [x for x in st.session_state["p_client"] if x in clients_dispo]
            st.session_state["p_client"] = valid_defaults_cli
            choix_client = st.multiselect("2. Client", clients_dispo, placeholder="Filtrer...", key="w_client", default=st.session_state["p_client"], on_change=sync_client)
            
        with c_mat:
            m_ext = df_opts_dynamic['EXT_Matiere'].dropna().unique().tolist()
            m_int = df_opts_dynamic['Matiere_T'].dropna().unique().tolist()
            matieres_dispo = ["Tous"] + sorted(list(set(m_ext + m_int)))
            valid_defaults_mat = [x for x in st.session_state["p_matiere"] if x in matieres_dispo]
            st.session_state["p_matiere"] = valid_defaults_mat
            choix_matiere = st.multiselect("3. Matière", matieres_dispo, placeholder="Filtrer...", key="w_matiere", default=st.session_state["p_matiere"], on_change=sync_matiere)
            
        with c_act:
            activites_dispo = ["Tous"] + sorted(df_opts_dynamic['Activité'].fillna("").unique().tolist())
            valid_defaults_act = [x for x in st.session_state["p_activite"] if x in activites_dispo]
            st.session_state["p_activite"] = valid_defaults_act
            choix_activite = st.multiselect("4. Activité", activites_dispo, placeholder="Filtrer...", key="w_activite", default=st.session_state["p_activite"], on_change=sync_activite)

    df_final = df_filtered_date.copy()

    if choix_exutoire and "Tous" not in choix_exutoire:
        df_final = df_final[df_final['Exutoire'].isin(choix_exutoire)]
    
    if choix_client and "Tous" not in choix_client:
        df_final = df_final[df_final['INT Client'].astype(str).isin(choix_client)]
        
    if choix_matiere and "Tous" not in choix_matiere:
        mask_mat = (df_final['EXT_Matiere'].astype(str).isin(choix_matiere)) | \
                   (df_final['Matiere_T'].astype(str).isin(choix_matiere))
        df_final = df_final[mask_mat]
        
    if choix_activite and "Tous" not in choix_activite:
        df_final = df_final[df_final['Activité'].astype(str).isin(choix_activite)]

    if search_ticket:
        df_final = df_final[df_final['Num Ticket'].astype(str).str.contains(search_ticket, case=False, na=False)]
    if search_bon:
        df_final = df_final[df_final['Num Bon'].astype(str).str.contains(search_bon, case=False, na=False)]

    st.divider()

    if 'Verif_Exutoire' in df_final.columns: df_ok_exu = df_final[df_final['Verif_Exutoire'] == 'OK']
    else: df_ok_exu = df_final

    k1, k2, k3, k4 = st.columns(4)
    
    def style_zebra(styler):
        return styler.apply(lambda x: ['background-color: rgba(128, 128, 128, 0.1)' if i % 2 != 0 else '' for i in range(len(x))], axis=0)

    with k1:
        st.caption("🏭 Vérif Exutoire")
        if not df_final.empty: 
            st.dataframe(
                style_zebra(pd.crosstab(df_final['Exutoire'], df_final['Verif_Exutoire'], margins=True, margins_name="Tot").style), 
                use_container_width=True
            )
    with k2:
        st.caption("⚖️ Vérif Tonnes")
        if not df_ok_exu.empty: 
            st.dataframe(
                style_zebra(pd.crosstab(df_ok_exu['Exutoire'], df_ok_exu['Verif_Tonnes'], margins=True, margins_name="Tot").style), 
                use_container_width=True
            )
    with k3:
        st.caption("🏢 Vérif Client")
        if not df_ok_exu.empty: 
            st.dataframe(
                style_zebra(pd.crosstab(df_ok_exu['Exutoire'], df_ok_exu['Verif_Client'], margins=True, margins_name="Tot").style), 
                use_container_width=True
            )
    with k4:
        st.caption("♻️ Vérif Matière")
        if not df_ok_exu.empty: 
            st.dataframe(
                style_zebra(pd.crosstab(df_ok_exu['Exutoire'], df_ok_exu['Verif_Matiere'], margins=True, margins_name="Tot").style), 
                use_container_width=True
            )

    st.divider()
    
    rename_map = {
        'Matiere_T': 'INT Mat', 'EXT_Matiere': 'EXT Mat',
        'Poids_Terrain': 'INT T.', 'Poids_Facture': 'EXT T.',
        'Verif_Exutoire': 'V. Exu', 'Verif_Tonnes': 'V. T.',
        'Verif_Matiere': 'V. Mat', 'Verif_Client': 'V. Cli',
        'Num Ticket': 'Ticket', 'Num Bon': 'Bon',
        'Immatriculation': 'Immat', 'Activité': 'Activ.'
    }
    df_disp = df_final.rename(columns=rename_map)
    # Ensure Date is actually date/datetime objects for the column_config to work
    if 'Date' in df_disp.columns: 
        df_disp['Date'] = pd.to_datetime(df_disp['Date'], errors='coerce')

    col_cfg = {}
    for col in df_disp.columns:
        if col in ['INT T.', 'EXT T.', 'Ecart']: col_cfg[col] = st.column_config.NumberColumn(col, width="small", format="%.2f")
        elif col == 'Date': col_cfg[col] = st.column_config.DateColumn(col, width="small", format="DD/MM/YYYY")
        else: col_cfg[col] = st.column_config.TextColumn(col, width="small")

    cols_global = ['Date', 'Ticket', 'Bon', 'Exutoire', 'Activ.', 'INT Client', 'EXT Client', 'INT Mat', 'EXT Mat', 'Immat', 'Chauffeur', 'V. Exu', 'V. T.', 'V. Mat', 'V. Cli', 'INT T.', 'EXT T.', 'Ecart']
    cols_tonnage = ['Date', 'Ticket','Bon', 'Exutoire','Activ.', 'Client','Immat', 'Chauffeur', 'INT T.', 'EXT T.', 'Ecart']
    cols_client = ['Date', 'Ticket','Bon', 'Exutoire', 'Activ.', 'Immat', 'Chauffeur', 'INT Client', 'EXT Client', 'INT T.', 'EXT T.']
    cols_matiere = ['Date', 'Ticket', 'Bon','Exutoire', 'Activ.', 'Immat', 'Chauffeur', 'INT Mat', 'EXT Mat', 'INT T.', 'EXT T.']
    cols_exutoire = ['Date', 'Ticket', 'Bon', 'Exutoire', 'Activ.', 'Immat', 'Chauffeur', 'INT Client', 'EXT Client', 'INT Mat', 'EXT Mat', 'INT T.', 'EXT T.', 'Ecart']

    def get_safe_cols(column_list, df_target):
        return [c for c in column_list if c in df_target.columns]

    
    df_err_exu_raw = df_final[df_final['Verif_Exutoire'] != 'OK']
    nb_err_exu = len(df_err_exu_raw[df_err_exu_raw['Validation_Exutoire'] == False])
    
    df_ok_exu = df_final[df_final['Verif_Exutoire'] == 'OK']
    
    df_err_ton_raw = df_ok_exu[df_ok_exu['Verif_Tonnes'] != 'OK']
    nb_err_ton = len(df_err_ton_raw[df_err_ton_raw['Validation_Tonnes'] == False])
    
    df_err_cli_raw = df_ok_exu[df_ok_exu['Verif_Client'] != 'OK']
    nb_err_cli = len(df_err_cli_raw[df_err_cli_raw['Validation_Client'] == False])
    
    df_err_mat_raw = df_ok_exu[df_ok_exu['Verif_Matiere'] != 'OK']
    nb_err_mat = len(df_err_mat_raw[df_err_mat_raw['Validation_Matiere'] == False])

    tab1, tab2, tab3, tab4, tab5= st.tabs([
        "🌍 Vue Globale", 
        f"🏭 Exutoire ({nb_err_exu})", 
        f"⚖️ Tonnage ({nb_err_ton})", 
        f"🏢 Client ({nb_err_cli})",
        f"♻️ Matière ({nb_err_mat})"
    ])
    
    def save_validations(edited_df, validation_col):
        """Helper to save validation changes"""
        
        
        
        if st.button(f"💾 Sauvegarder", key=f"save_{validation_col}", type="primary"):
            with engine.connect() as conn:
                try:
                    trans = conn.begin()
                    
                    updates = edited_df[['id', validation_col]].to_dict(orient='records')
                    
                    for row in updates:
                        val = 'TRUE' if row[validation_col] else 'FALSE'
                        
                        if validation_col == "Validation_Tonnes":
                            if val == 'TRUE':
                                # VALIDATION : Sauvegarde Poids Original (si pas déjà fait) + Ecrase Poids Terrain + Ecart 0 + Verif OK
                                stmt = text(f'''
                                    UPDATE {TABLE_NAME} 
                                    SET "{validation_col}" = TRUE, 
                                        "Poids_Terrain_Original" = COALESCE("Poids_Terrain_Original", "Poids_Terrain"), 
                                        "Poids_Terrain" = "Poids_Facture", 
                                        "Ecart" = 0,
                                        "Verif_Tonnes" = 'OK'
                                    WHERE id = :id
                                ''')
                            else:
                                # ANNULATION : Restaure Poids Original + Recalcule Ecart + Recalcule Status Verif + Reset Original
                                stmt = text(f'''
                                    UPDATE {TABLE_NAME} 
                                    SET "{validation_col}" = FALSE, 
                                        "Poids_Terrain" = COALESCE("Poids_Terrain_Original", "Poids_Terrain"), 
                                        "Ecart" = COALESCE("Poids_Terrain_Original", "Poids_Terrain") - "Poids_Facture",
                                        "Verif_Tonnes" = CASE 
                                            WHEN ABS(COALESCE("Poids_Terrain_Original", "Poids_Terrain") - "Poids_Facture") < 0.01 THEN 'OK' 
                                            ELSE 'Pb.T' 
                                        END,
                                        "Poids_Terrain_Original" = NULL
                                    WHERE id = :id
                                ''')
                        elif validation_col == "Validation_Matiere":
                            if val == 'TRUE':
                                stmt = text(f'''
                                    UPDATE {TABLE_NAME} 
                                    SET "{validation_col}" = TRUE, 
                                        "Matiere_T_Original" = COALESCE("Matiere_T_Original", "Matiere_T"), 
                                        "Matiere_T" = "EXT_Matiere", 
                                        "Verif_Matiere" = 'OK'
                                    WHERE id = :id
                                ''')
                            else:
                                stmt = text(f'''
                                    UPDATE {TABLE_NAME} 
                                    SET "{validation_col}" = FALSE, 
                                        "Matiere_T" = COALESCE("Matiere_T_Original", "Matiere_T"), 
                                        "Matiere_T_Original" = NULL,
                                        "Verif_Matiere" = 'Pb.Mat'
                                    WHERE id = :id
                                ''')
                        elif validation_col == "Validation_Client":
                            if val == 'TRUE':
                                stmt = text(f'''
                                    UPDATE {TABLE_NAME} 
                                    SET "{validation_col}" = TRUE, 
                                        "INT_Client_Original" = COALESCE("INT_Client_Original", "INT Client"), 
                                        "INT Client" = "EXT Client", 
                                        "Verif_Client" = 'OK'
                                    WHERE id = :id
                                ''')
                            else:
                                stmt = text(f'''
                                    UPDATE {TABLE_NAME} 
                                    SET "{validation_col}" = FALSE, 
                                        "INT Client" = COALESCE("INT_Client_Original", "INT Client"), 
                                        "INT_Client_Original" = NULL,
                                        "Verif_Client" = 'Pb.Clt'
                                    WHERE id = :id
                                ''')
                        else:
                             stmt = text(f'UPDATE {TABLE_NAME} SET "{validation_col}" = {val} WHERE id = :id')

                        conn.execute(stmt, {"id": row['id']})
                    
                    trans.commit()
                    st.success("Validations enregistrées !")
                    st.rerun()
                except Exception as e:
                    trans.rollback()
                    logger.error(f"Erreur SQL Validation: {e}", exc_info=True)
                    st.error(f"Erreur SQL: {e}")

    with tab1:
        t_int = df_final['Poids_Terrain'].sum()
        t_ext = df_final['Poids_Facture'].sum()
        t_ec = df_final['Ecart'].sum()
        
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Poids Terrain (T)", f"{t_int:,.2f}")
        c_m2.metric("Poids Facture (T)", f"{t_ext:,.2f}")
        c_m3.metric("Ecart Total (T)", f"{t_ec:,.2f}", delta_color="inverse")

        def highlight_rows(row):
            is_error = False
            for c in ['V. Exu', 'V. T.', 'V. Mat', 'V. Cli']:
                if c in row and str(row[c]).startswith('Pb'):
                    is_error = True
                    break
            
            if is_error:
                return ['background-color: #ffcccc'] * len(row)
            
            # Zebra pattern
            try:
                if int(row.name) % 2 != 0:
                    return ['background-color: rgba(128, 128, 128, 0.1)'] * len(row)
            except:
                pass
                
            return [''] * len(row)

        st.dataframe(
            df_disp[get_safe_cols(cols_global, df_disp)].reset_index(drop=True).style.apply(highlight_rows, axis=1), 
            use_container_width=True, 
            hide_index=True, 
            height=600, 
            column_config=col_cfg
        )


    with tab2:
        mask = df_disp['V. Exu'] != 'OK'
        df_view = df_disp[mask].copy()
        
        if not df_view.empty:
            st.error(f"Il y a {len(df_view)} erreurs d'exutoire (Dont {nb_err_exu} non validées).")
            
            df_view = df_view.sort_values(by='Validation_Exutoire', ascending=True)

            cols_edit = ['id', 'Validation_Exutoire'] + get_safe_cols(cols_exutoire, df_view)
            cfg_edit = col_cfg.copy()
            cfg_edit['Validation_Exutoire'] = st.column_config.CheckboxColumn("✅ Validé", help="Cochez pour ignorer cette erreur")
            cfg_edit['id'] = None  # Hide ID
            
            edited = st.data_editor(
                df_view[cols_edit].style.apply(lambda r: highlight_validated_rows(r, 'Validation_Exutoire'), axis=1), 
                hide_index=True,
                use_container_width=True,
                column_config=cfg_edit, 
                disabled=get_safe_cols(cols_exutoire, df_view), # Only Checkbox editable
                key="editor_exutoire"
            )
            save_validations(edited, 'Validation_Exutoire')
        else: st.success("RAS Exutoire.")

    with tab3:
        
        mask = (df_disp['V. Exu'] == 'OK') & (df_disp['V. T.'] != 'OK')
        df_view = df_disp[mask].copy()
        
        if not df_view.empty:
            st.warning(f"Il y a {len(df_view)} lignes avec écarts (Dont {nb_err_ton} non validées).")
            
            df_view = df_view.sort_values(by='Validation_Tonnes', ascending=True)

            cols_edit = ['id', 'Validation_Tonnes'] + get_safe_cols(cols_tonnage, df_view)
            cfg_edit = col_cfg.copy()
            cfg_edit['Validation_Tonnes'] = st.column_config.CheckboxColumn("✅ Validé", help="Cochez pour ignorer cette erreur")
            cfg_edit['id'] = None # Hide ID
            
            edited = st.data_editor(
                df_view[cols_edit].style.apply(lambda r: highlight_validated_rows(r, 'Validation_Tonnes'), axis=1), 
                hide_index=True,
                use_container_width=True,
                column_config=cfg_edit, 
                disabled=get_safe_cols(cols_tonnage, df_view), # Only Checkbox editable
                key="editor_tonnes"
            )
            save_validations(edited, 'Validation_Tonnes')
            
        else: st.success("RAS Tonnage.")

    with tab4:
        mask = (df_disp['V. Exu'] == 'OK') & (df_disp['V. Cli'] != 'OK')
        df_view = df_disp[mask].copy()
        
        if not df_view.empty:
            st.warning(f"Il y a {len(df_view)} erreurs Client (Dont {nb_err_cli} non validées).")
            
            df_view = df_view.sort_values(by='Validation_Client', ascending=True)

            cols_edit = ['id', 'Validation_Client'] + get_safe_cols(cols_client, df_view)
            cfg_edit = col_cfg.copy()
            cfg_edit['Validation_Client'] = st.column_config.CheckboxColumn("✅ Validé", help="Cochez pour ignorer cette erreur")
            cfg_edit['id'] = None # Hide ID
            
            edited = st.data_editor(
                df_view[cols_edit].style.apply(lambda r: highlight_validated_rows(r, 'Validation_Client'), axis=1), 
                hide_index=True,
                use_container_width=True,
                column_config=cfg_edit,
                disabled=get_safe_cols(cols_client, df_view),
                key="editor_client"
            )
            save_validations(edited, 'Validation_Client')
        else: st.success("RAS Client.")

    with tab5:
        mask = (df_disp['V. Exu'] == 'OK') & (df_disp['V. Mat'] != 'OK')
        df_view = df_disp[mask].copy()
        
        if not df_view.empty:
            st.warning(f"Il y a {len(df_view)} divergences de matière (Dont {nb_err_mat} non validées).")
            
            df_view = df_view.sort_values(by='Validation_Matiere', ascending=True)

            cols_edit = ['id', 'Validation_Matiere'] + get_safe_cols(cols_matiere, df_view)
            cfg_edit = col_cfg.copy()
            cfg_edit['Validation_Matiere'] = st.column_config.CheckboxColumn("✅ Validé", help="Cochez pour ignorer cette erreur")
            cfg_edit['id'] = None # Hide ID

            edited = st.data_editor(
                df_view[cols_edit].style.apply(lambda r: highlight_validated_rows(r, 'Validation_Matiere'), axis=1), 
                hide_index=True,
                use_container_width=True,
                column_config=cfg_edit,
                disabled=get_safe_cols(cols_matiere, df_view),
                key="editor_matiere"
            )
            save_validations(edited, 'Validation_Matiere')
        else: st.success("RAS Matière.")

st.sidebar.title("MENU PRINCIPAL")

cookie_manager = stx.CookieManager()
cookies = cookie_manager.get_all()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    auth_user_cookie = cookie_manager.get("auth_user")
    if auth_user_cookie:
        st.session_state["authenticated"] = True
        st.session_state["username"] = auth_user_cookie

if not st.session_state["authenticated"]:
    login_screen()
else:
    st.sidebar.title(f"👤 {st.session_state['username']}")
    if st.sidebar.button("Se déconnecter"):
        logout()
        
    if "active_domain" not in st.session_state:
        st.session_state["active_domain"] = "🚛 Suivi Exutoire"

    def clear_app_state():
        for key in list(st.session_state.keys()):
            # Clear dataframes and results when changing menu
            if key.startswith('df_') or key == 'verif_heures_results':
                del st.session_state[key]

    st.sidebar.title("Navigation")
    
    domain = st.sidebar.radio("Domaine :", ["🚛 Flux Exutoire", "👥 Gestion d'Activité", "📖 Manuel Utilisateur"], on_change=clear_app_state)
    
    if domain == "🚛 Flux Exutoire":
        options_exutoire = ["📊 Tableau de Bord Exutoire", "⚖️ Vérification Tonnages", "♻️ Vérification Ecorec", "⚙️ Administration"]
        categorie = st.sidebar.radio("Menu :", options_exutoire, on_change=clear_app_state)
        
    elif domain == "👥 Gestion d'Activité": # Heures
        options_heures = ["📥 Import des fichiers", "📅 Suivi de Présences", "📈 Statistiques"]
        categorie = st.sidebar.radio("Menu :", options_heures, on_change=clear_app_state)
        st.sidebar.info("Module de gestion opérationnelle.")
        
    elif domain == "📖 Manuel Utilisateur":
        categorie = "📖 Manuel Utilisateur"

    # Mapping to old logic
    if categorie == "📊 Tableau de Bord Exutoire":
        categorie = "📊 Tableau de Bord" # Map back to internal string if needed?
        pass 

    engine = get_db_engine()
    if engine:
        check_and_migrate_db(engine)

    if categorie == "📊 Tableau de Bord Exutoire" or categorie == "📊 Tableau de Bord":
        interface_dashboard()
        
    elif categorie == "📖 Manuel Utilisateur":
        st.title("📖 Manuel d'Utilisation")
        try:
            # We look for the manual in the correct location
            manual_path = "modules/MANUEL_UTILISATEUR.md" 
            if not os.path.exists(manual_path): manual_path = "MANUEL_UTILISATEUR.md"
            with open(manual_path, "r", encoding="utf-8") as f:
                content = f.read()
            st.markdown(content)
        except Exception as e:
            st.error(f"Le manuel n'a pas pu être chargé : {e}")
            
    elif categorie == "♻️ Vérification Ecorec":
        show_verif_ecorec_ui()
        
    elif categorie == "⚖️ Vérification Tonnages":
        # Keep the provider selection in sidebar as requested by "garde les même chose"
        provider = st.sidebar.radio("Choisir le prestataire", sorted(["DUPILLE", "PICHETA GPSEO", "PICHETA INOE", "PICHETA SMIRTOM", "PICHETA VALOSEINE", "SUEZ", "VALENE", "AZALYS SOTREMA", "AZALYS VALOSEINE", "VALOSEINE ENC GPSEO", "VERT COMPOST SMIRTOM", "SATEL SMIRTOM ENC"]), on_change=clear_app_state)
        st.divider()
    
        if provider == "DUPILLE":
            st.title("Import DUPILLE")
            c1, c2 = st.columns(2)
            f_lb = c1.file_uploader("Fichier Terrain", type=['xlsx', 'xls', 'xlsm'])
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xlsm'])
            if st.button("Lancer") and f_lb and f_fac:
                st.session_state['df_dupille'] = process_dupille(f_lb, f_fac)

            if 'df_dupille' in st.session_state:
                df = st.session_state['df_dupille']
                display_results(df)
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "PICHETA GPSEO":
            st.title("Import PICHETA GPSEO")
            c1, c2 = st.columns(2)
            with c1:
                f_ctc = st.file_uploader("Fichier CTC", type=['xlsx', 'xls', 'xlsm'])
                f_exp = st.file_uploader("Export Facture", type=['xlsx', 'xls', 'xlsm'])
            with c2:
                f_dech = st.file_uploader("Fichier DECH", type=['xlsx', 'xls', 'xlsm'])
            
            if st.button("Lancer") and f_exp:
                with st.spinner("Matching intelligent en cours..."):
                    st.session_state['df_picheta'] = process_picheta(f_ctc, f_dech, f_exp)

            if 'df_picheta' in st.session_state:
                df = st.session_state['df_picheta']
                display_results(df)
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "VALENE":
            st.title("Import VALENE")
            c1, c2, c3 = st.columns(3)
            f_pap = c1.file_uploader("PAP", type=['xlsx', 'xls', 'xlsm'])
            f_pav = c2.file_uploader("PAV", type=['xlsx', 'xls', 'xlsm'])
            f_sot = c3.file_uploader("SOTREMA2", type=['xlsx', 'xls', 'xlsm'])
            f_exp = st.file_uploader("Export Facture", type=['xlsx', 'xls', 'xlsm'])
            if st.button("Lancer") and f_exp:
                st.session_state['df_valene'] = process_valene(f_pap, f_pav, f_sot, f_exp)

            if 'df_valene' in st.session_state:
                df = st.session_state['df_valene']
                display_results(df)
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "PICHETA VALOSEINE":
            st.title("Import PICHETA VALOSEINE")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'])
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'])
            
            if f_ter and f_fac:
                if st.button("Lancer Picheta Valoseine"):
                    final = process_valoseine(f_ter, f_fac)
                    st.session_state['df_valoseine'] = final
            
            if 'df_valoseine' in st.session_state:
                df = st.session_state['df_valoseine']
                display_results(df)
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "PICHETA SMIRTOM":
            st.title("Import PICHETA SMIRTOM")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'])
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'])
            
            if st.button("Lancer") and f_ter and f_fac:
                st.session_state['df_picheta_smirtom'] = process_picheta_smirtom(f_ter, f_fac)
                
            if 'df_picheta_smirtom' in st.session_state:
                df = st.session_state['df_picheta_smirtom']
                display_results(df)
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")


        elif provider == "PICHETA INOE":
            st.title("Import PICHETA INOE")
            c1, c2 = st.columns(2)
            f_ctc = c1.file_uploader("Fichier CTC (XLS)", type=['xls', 'xlsx'])
            f_dech = c2.file_uploader("Fichier Dechetterie (XLS)", type=['xls', 'xlsx'])
            st.divider()
            f_inv = st.file_uploader("Fichier Facture (XLSX)", type=['xlsx'])
            
            if st.button("Lancer", type="primary") and f_inv and (f_ctc or f_dech):
                 st.session_state['df_inoe'] = process_picheta_inoe(f_ctc, f_dech, f_inv)
            
            if 'df_inoe' in st.session_state:
                df = st.session_state['df_inoe']
                display_results(df)
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "SUEZ":
            st.title("Import SUEZ")
            start_col, end_col = st.columns(2)
            f_ctc = start_col.file_uploader("Fichier CTC", type=['xlsx', 'xls', 'xlsm'])
            f_dech = end_col.file_uploader("Fichier DECH", type=['xlsx', 'xls', 'xlsm'])
            f_fac = st.file_uploader("Listing GPSEO (Facture)", type=['xlsx', 'xls', 'xlsm'])
            if st.button("Lancer") and f_fac:
                st.session_state['df_suez'] = process_suez(f_ctc, f_dech, f_fac)

            if 'df_suez' in st.session_state:
                df = st.session_state['df_suez']
                df_view = df.copy()
                st.caption(f"Lignes affichées : {len(df_view)} / {len(df)}")
                display_results(df)
                
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")
    
        elif provider == "AZALYS SOTREMA":
            st.title("Import AZALYS SOTREMA")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'], key="as_t")
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'], key="as_f")
            
            if st.button("Lancer Azalys Sotrema"):
                if f_ter and f_fac:
                    final = process_azalys(f_ter, f_fac, "AZALYS SOTREMA")
                    st.session_state['df_azalys_sotrema'] = final
                    
            if 'df_azalys_sotrema' in st.session_state:
                 df = st.session_state['df_azalys_sotrema']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_as"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "AZALYS VALOSEINE":
            st.title("Import AZALYS VALOSEINE")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'], key="av_t")
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'], key="av_f")
            
            if st.button("Lancer Azalys Valoseine"):
                if f_ter and f_fac:
                    final = process_azalys(f_ter, f_fac, "AZALYS VALOSEINE")
                    st.session_state['df_azalys_valoseine'] = final

            if 'df_azalys_valoseine' in st.session_state:
                 df = st.session_state['df_azalys_valoseine']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_av"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")



        elif provider == "VALOSEINE ENC GPSEO":
            st.title("Import VALOSEINE ENC GPSEO")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'], key="ve_t")
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'], key="ve_f")
            
            if st.button("Lancer Valoseine ENC"):
                if f_ter and f_fac:
                    final = process_valoseine_enc(f_ter, f_fac)
                    st.session_state['df_valoseine_enc'] = final
                    
            if 'df_valoseine_enc' in st.session_state:
                 df = st.session_state['df_valoseine_enc']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_ve"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "VERT COMPOST SMIRTOM":
            st.title("Import VERT COMPOST SMIRTOM")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'], key="vcs_t")
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'], key="vcs_f")
            
            if st.button("Lancer Vert Compost"):
                if f_ter and f_fac:
                    final = process_vert_compost_smirtom(f_ter, f_fac)
                    st.session_state['df_vert_compost'] = final
                    
            if 'df_vert_compost' in st.session_state:
                 df = st.session_state['df_vert_compost']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_vcs"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider == "SATEL SMIRTOM ENC":
            st.title("Import SATEL SMIRTOM ENC")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain (XLS)", type=['xls', 'xlsx'], key="sse_t")
            f_fac = c2.file_uploader("Fichier Facture (XLSX)", type=['xlsx', 'xls'], key="sse_f")
            
            if st.button("Lancer SATEL SMIRTOM ENC"):
                if f_ter and f_fac:
                    final = process_satel_smirtom_enc(f_ter, f_fac)
                    st.session_state['df_satel_smirtom_enc'] = final
                    
            if 'df_satel_smirtom_enc' in st.session_state:
                 df = st.session_state['df_satel_smirtom_enc']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_sse"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")
    
    elif categorie in ["📥 Import des fichiers", "📅 Suivi de Présences", "📈 Statistiques"]:
        show_verif_heures_ui(engine, mode=categorie)

    elif categorie == "⚙️ Administration":
        interface_admin()
