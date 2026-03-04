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

# =============================================================================
# IMPORTS DES MODULES DE TRAITEMENT (MODULARISATION)
# =============================================================================
from modules.verif_suez import charger_suez_terrain, process_suez, normalize_site_key, check_site_keys
from modules.verif_picheta import charger_picheta, process_picheta
from modules.verif_valene import charger_valene, process_valene
from modules.verif_azalys import charger_azalys, process_azalys, charger_valoseine_enc, process_valoseine_enc
from modules.verif_vert_compost_smirtom import charger_vert_compost_smirtom, process_vert_compost_smirtom
from modules.verif_dupille import charger_dupille, charger_dupille_facture, process_dupille
from modules.verif_satel import charger_satel_smirtom_enc, process_satel_smirtom_enc
from modules.models_prestataires import get_prestataires_dynamiques
from modules.admin_prestataires_ui import show_admin_prestataires_ui
from modules.verif_generique import process_generique

# =============================================================================
# UTILITAIRES COMMUNS
# =============================================================================

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

# Logic for DUPILLE moved to modules/verif_dupille.py


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

from modules.verif_picheta import process_picheta, charger_picheta
# Picheta logic moved to modules/verif_picheta.py


# Valene logic moved to modules/verif_valene.py

# Additional modularization cleanup


# (charger_suez_terrain moved to modules/verif_suez.py)

# Suez logic moved to modules/verif_suez.py


from modules.verif_valene import charger_valoseine, process_valoseine
# Valoseine logic moved to modules/verif_valene.py


from modules.verif_picheta import process_picheta_smirtom, charger_picheta_smirtom
# Smirtom logic moved to modules/verif_picheta.py

from modules.verif_picheta import charger_picheta_inoe, process_picheta_inoe
# Picheta Inoe logic moved to modules/verif_picheta.py


def display_results(df):
    if df.empty:
        st.warning("Aucun résultat.")
        return

    def highlight_method(row):
        m = str(row.get('Methode', ''))
        if 'Auto' in m or 'Intelligent' in m: return ['background-color: #d4edda; color: #155724'] * len(row)
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

from modules.verif_azalys import charger_azalys, process_azalys
# Azalys logic moved to modules/verif_azalys.py



from modules.verif_azalys import charger_valoseine_enc, process_valoseine_enc
# Valoseine ENC logic moved to modules/verif_azalys.py



from modules.verif_vert_compost_smirtom import charger_vert_compost_smirtom, process_vert_compost_smirtom
# SMIRTOM Vert/Compost logic moved to modules/verif_vert_compost_smirtom.py



# Logic for SATEL SMIRTOM ENC moved to modules/verif_satel.py


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
        
        exu_del = c_exu_del.selectbox("Exutoire concerné", ["Sélectionner..."] + ["DUPILLE", "PICHETA GPSEO", "VALENE", "SUEZ"])
        dates_del = c_dates_del.date_input("Période cible", [])
        
        motif_del = st.text_input("Motif de l'opération", "")
        
        if st.button("Exécuter l'archivage", type="primary"):
            if exu_del == "Sélectionner..." or len(dates_del) != 2:
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
        # Fetch dynamic providers
        prestataires_dynamiques = get_prestataires_dynamiques(engine)
        noms_dynamiques = [p['nom'] for p in prestataires_dynamiques] if prestataires_dynamiques else []
        tous_prestataires = sorted(["DUPILLE", "PICHETA GPSEO", "PICHETA INOE", "PICHETA SMIRTOM", "PICHETA VALOSEINE", "SUEZ", "VALENE", "AZALYS SOTREMA", "AZALYS VALOSEINE", "VERT COMPOST SMIRTOM", "SATEL SMIRTOM ENC"] + noms_dynamiques)

        provider = st.sidebar.radio("Choisir le prestataire", tous_prestataires, on_change=clear_app_state)
        st.divider()

    
        if provider == "DUPILLE":
            st.title("Import Dupille")
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
            f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'])
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'])
            
            if f_ter and f_fac:
                if st.button("Lancer"):
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
            f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'])
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'])
            
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
            f_ctc = c1.file_uploader("Fichier CTC", type=['xls', 'xlsx'])
            f_dech = c2.file_uploader("Fichier Dechetterie", type=['xls', 'xlsx'])
            st.divider()
            f_inv = st.file_uploader("Fichier Facture", type=['xlsx'])
            
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
            f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'], key="as_t")
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'], key="as_f")
            
            if st.button("Lancer"):
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
            f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'], key="av_t")
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'], key="av_f")
            
            if st.button("Lancer"):
                if f_ter and f_fac:
                    final = process_azalys(f_ter, f_fac, "AZALYS VALOSEINE")
                    st.session_state['df_azalys_valoseine'] = final

            if 'df_azalys_valoseine' in st.session_state:
                 df = st.session_state['df_azalys_valoseine']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_av"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")



        # elif provider == "VALOSEINE ENC GPSEO":
        #     st.title("Import VALOSEINE ENC GPSEO")
        #     c1, c2 = st.columns(2)
        #     f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'], key="ve_t")
        #     f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'], key="ve_f")
            
        #     if st.button("Lancer"):
        #         if f_ter and f_fac:
        #             final = process_valoseine_enc(f_ter, f_fac)
        #             st.session_state['df_valoseine_enc'] = final
                    
        #     if 'df_valoseine_enc' in st.session_state:
        #          df = st.session_state['df_valoseine_enc']
        #          display_results(df)
        #          if st.button("💾 Enregistrer tout en Base", type="primary", key="save_ve"): 
        #             save_to_db(df, engine)
        #             st.success("Données enregistrées avec succès !")

        elif provider == "VERT COMPOST SMIRTOM":
            st.title("Import VERT COMPOST SMIRTOM")
            c1, c2 = st.columns(2)
            f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'], key="vcs_t")
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'], key="vcs_f")
            
            if st.button("Lancer"):
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
            f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'], key="sse_t")
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xls'], key="sse_f")
            
            if st.button("Lancer"):
                if f_ter and f_fac:
                    final = process_satel_smirtom_enc(f_ter, f_fac)
                    st.session_state['df_satel_smirtom_enc'] = final
                    
            if 'df_satel_smirtom_enc' in st.session_state:
                 df = st.session_state['df_satel_smirtom_enc']
                 display_results(df)
                 if st.button("💾 Enregistrer tout en Base", type="primary", key="save_sse"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

        elif provider in noms_dynamiques:
            # Traitement Dynamique
            st.title(f"Import {provider}")
            
            # Find provider config
            presta_config = next((p for p in prestataires_dynamiques if p['nom'] == provider), None)
            
            if presta_config:
                c1, c2 = st.columns(2)
                f_ter = c1.file_uploader("Fichier Terrain", type=['xls', 'xlsx'], key=f"dyn_t_{provider}")
                f_fac = c2.file_uploader(f"Fichier Facture", type=['xlsx', 'xls'], key=f"dyn_f_{provider}")
                
                if st.button("Lancer", type="primary"):
                    if f_ter and f_fac:
                        with st.spinner(f"Traitement dynamique {provider}..."):
                            final = process_generique(f_ter, f_fac, provider, presta_config['header_row'], presta_config)
                            st.session_state[f'df_dyn_{provider}'] = final
                        
                if f'df_dyn_{provider}' in st.session_state:
                     df = st.session_state[f'df_dyn_{provider}']
                     display_results(df)
                     
                     if st.button("💾 Enregistrer tout en Base", type="primary", key=f"save_dyn_{provider}"): 
                        save_to_db(df, engine)
                        st.success("Données enregistrées avec succès !")
            else:
                st.error("Configuration du prestataire introuvable.")
    
    elif categorie in ["📥 Import des fichiers", "📅 Suivi de Présences", "📈 Statistiques"]:
        show_verif_heures_ui(engine, mode=categorie)

    elif categorie == "⚙️ Administration":
        tab_admin, tab_presta = st.tabs(["🔒 Utilisateurs", "⚙️ Modèles Prestataires"])
        with tab_admin:
            interface_admin()
        with tab_presta:
            show_admin_prestataires_ui(engine)
