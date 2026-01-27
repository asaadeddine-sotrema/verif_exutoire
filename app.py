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

# --- CONFIGURATION ---
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

# --- DB CONNECTION ---
@st.cache_resource
def get_db_engine():
    try:
        url = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
        return create_engine(url)
    except Exception as e:
        st.error(f"Erreur Connexion DB: {e}")
        return None

def check_and_migrate_db(engine):
    """MIGRATION AUTO : Ajoute isActive, Motif et Dernier_Utilisateur si manquants"""
    try:
        with engine.connect() as conn:
            columns_to_add = {
                "isActive": "BOOLEAN DEFAULT TRUE",
                "Motif": "TEXT",
                "Dernier_Utilisateur": "TEXT"
            }
            
            for col, col_type in columns_to_add.items():
                res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{TABLE_NAME}' AND column_name = '{col}'"))
                if res.rowcount == 0:
                    conn.execute(text(f'ALTER TABLE {TABLE_NAME} ADD COLUMN "{col}" {col_type}'))
                    conn.commit()
                    st.toast(f"✅ Migration : Colonne '{col}' ajoutée.")
    except Exception as e:
        st.error(f"Erreur Migration : {e}")

def login_screen():
    """Affiche un écran de connexion"""
    st.markdown("""<style>.login-box { padding: 2rem; border-radius: 10px; border: 1px solid #ddd; }</style>""", unsafe_allow_html=True)
    
    with st.container():
        st.title("🔐 Connexion")
        user = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        
        # Récupération sécurisée des identifiants multiples (JSON dans .env)
        env_users_json = os.getenv("APP_USERS")
        
        VALID_USERS = {}
        if env_users_json:
            try:
                VALID_USERS = json.loads(env_users_json)
            except json.JSONDecodeError:
                st.error("Erreur de configuration : APP_USERS n'est pas un JSON valide.")
        
        if st.button("Se connecter", type="primary"):
            # Vérification sécurisée avec bcrypt
            try:
                # Convertion en bytes pour bcrypt
                if user in VALID_USERS and bcrypt.checkpw(password.encode('utf-8'), VALID_USERS[user].encode('utf-8')):
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = user
                    st.rerun()
                else:
                    st.error("Identifiant ou mot de passe incorrect")
            except Exception as e:
                st.error("Erreur d'authentification (vérifiez le format des mots de passe).")

def logout():
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    st.rerun()

# =============================================================================
# 1. UTILITAIRES
# =============================================================================

def nettoyer_texte(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def convertir_date_robuste(val):
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime.date)): return val
    try:
        val_num = float(val)
        if val_num > 30000: return pd.to_datetime(val_num, unit='D', origin='1899-12-30').date()
    except: pass
    try: return pd.to_datetime(val, format='%Y-%m-%d').date()
    except: pass
    try: return pd.to_datetime(val, dayfirst=True).date()
    except: return pd.NaT

def normaliser_matiere_dupille(valeur_origine):
    val = nettoyer_texte(valeur_origine)
    if "VERTS" in val or "VEGETAUX" in val: return "DECHETS VERTS"
    if "BOIS" in val: return "BOIS"
    if any(x in val for x in ["DECHETS IND", "ORDURES MEN"]): return "ORDURES MENAGERES"
    return val

def normaliser_matiere_valene(valeur_origine):
    val = nettoyer_texte(valeur_origine)
    if any(x in val for x in ["DECHETS IND", "ORDURES MEN", "DIB", "O.M"]): return "ORDURES MENAGERES"
    if any(x in val for x in ["EMBALLAGES", "RECYCLABLES", "TRI SELECTIF"]): return "EMBALLAGES MENAGERS RECUPEREES"
    if "VERRE" in val: return "VERRE"
    if "CARTON" in val: return "CARTON"
    if "BOIS" in val: return "BOIS"
    return val

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

def save_to_db(df, engine):
    """Sauvegarde intelligente v3 : Gestion isActive et Résurrection"""
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
        df_export = df_export.drop_duplicates(subset=['Num Ticket', 'Exutoire'], keep='last')

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
            update_dict = {c.name: c for c in stmt.excluded if c.name not in ['Num Ticket', 'Exutoire']}
            update_dict['isActive'] = True 
            
            stmt = stmt.on_conflict_do_update(
                index_elements=['Num Ticket', 'Exutoire'],
                set_=update_dict
            )
            result = conn.execute(stmt)
            conn.commit()
            st.success(f"✅ Données sauvegardées avec succès ({result.rowcount} lignes traitées).")
                
    except Exception as e:
        st.error(f"Erreur Technique : {e}")

# =============================================================================
# 2. MODULE DUPILLE
# =============================================================================
def process_dupille(f_lb, f_fac):
    temp = pd.read_excel(f_lb, header=None, nrows=15)
    idx = 0
    for i, r in temp.iterrows(): 
        if "Num Ticket" in str(r.values): idx = i; break
    f_lb.seek(0)
    df_lb = pd.read_excel(f_lb, header=idx)
    
    cols = {'Description': 'Matiere_T', 'Poids en Tonnes': 'Poids_Terrain', 'Exutoire': 'Client', 'Date': 'Date_Ref'}
    for c in df_lb.columns:
        if "bon" in str(c).lower(): cols[c] = "Num Bon"
        if "chauffeur" in str(c).lower(): cols[c] = "Chauffeur"
        if "immat" in str(c).lower(): cols[c] = "Immatriculation"
    df_lb = df_lb.rename(columns=cols)
    df_lb['Num Ticket'] = df_lb['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)
    df_lb['Activité'] = "LB_DUPILLE"

    xls = pd.ExcelFile(f_fac)
    frames = []
    for sheet in xls.sheet_names:
        if "pap" in str(sheet).lower():
            d = pd.read_excel(f_fac, sheet_name=sheet, header=None)
            if len(d.columns) > 7:
                d = d.rename(columns={0: 'Num Ticket', 1: 'Date_Ref', 2: 'Client', 6: 'EXT_Matiere', 7: 'net'})
                d['Activité'] = "PAP"
                frames.append(d)
        else:
            d_head = pd.read_excel(f_fac, sheet_name=sheet, header=None, nrows=10)
            idx = 0
            for i, r in d_head.iterrows():
                if "ID" in str(r.values): idx = i; break
            d = pd.read_excel(f_fac, sheet_name=sheet, header=idx)
            d = d.rename(columns={'ID': 'Num Ticket', 'lib_produit': 'EXT_Matiere', 'lib_client': 'Client', 'Dates': 'Date_Ref'})
            d['Activité'] = "DECHETTERIE"
            frames.append(d)
    
    df_fac = pd.concat(frames, ignore_index=True)
    if 'net' in df_fac.columns: df_fac['Poids_Facture'] = pd.to_numeric(df_fac['net'], errors='coerce') / 1000
    df_fac['Num Ticket'] = df_fac['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)

    df_lb['Matiere_T'] = df_lb['Matiere_T'].apply(normaliser_matiere_dupille)
    df_fac['EXT_Matiere'] = df_fac.get('EXT_Matiere', '').apply(normaliser_matiere_dupille)

    merged = pd.merge(df_lb, df_fac, on='Num Ticket', suffixes=('_T', '_F'), how='outer', indicator=True)
    
    merged['Exutoire'] = "DUPILLE"
    merged['Poids_Terrain'] = pd.to_numeric(merged['Poids_Terrain'], errors='coerce').fillna(0)
    merged['Poids_Facture'] = pd.to_numeric(merged['Poids_Facture'], errors='coerce').fillna(0)
    merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
    
    merged['Date_Ref'] = merged['Date_Ref_F'].fillna(merged['Date_Ref_T']).apply(convertir_date_robuste)
    merged['Client'] = merged['Client_F'].fillna(merged['Client_T'])
    merged['INT Client'] = merged.get('Client_T', '')
    merged['EXT Client'] = merged.get('Client_F', '')

    merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
    merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere']).replace({True:'OK', False:'Pb.Mat'})
    merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})

    def verif_client(row):
        c_int = str(row.get('INT Client', '')).upper().strip()
        c_ext = str(row.get('EXT Client', '')).upper().strip()
        if not c_int or not c_ext: return "OK"
        if "GPSO" in c_ext and "DUPILLE SARL (CU GPSO)" in c_int: return "OK"
        if "DUPILLE SARL (CU GPSO)" in c_int and "GPSO" in c_ext: return "OK"
        if c_int in c_ext or c_ext in c_int: return "OK"
        return "Pb.Clt"
    
    merged['Verif_Client'] = merged.apply(verif_client, axis=1)
    
    if 'Num Bon' in merged.columns:
        merged['Num Bon'] = merged['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
    return merged

# =============================================================================
# 3. MODULE PICHETA
# =============================================================================

def restore_columns(df, suffix, original_cols):
    cols = {}
    for c in df.columns:
        if c.endswith(suffix):
            base_name = c[:-len(suffix)]
            cols[c] = base_name
    for c in original_cols:
        if c in df.columns and c not in cols.values():
            cols[c] = c
    return df[list(cols.keys())].rename(columns=cols)

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
    df_ref = pd.read_excel(f_exp, header=idx_ref) 
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower()
        if "document" in cl or "n° bon" in cl: cols_ref[c] = "Num Ticket"
        if "q liv" in cl or "poids" in cl: cols_ref[c] = "Poids_Facture"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "immat" in cl: cols_ref[c] = "Immatriculation"
    
    df_ref = df_ref.rename(columns=cols_ref)
    
    if 'TEMP_CodeAdresse' in df_ref.columns:
        df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETTERIE PICHETA')
    else:
        df_ref['Client'] = "DECHETTERIE PICHETA"

    df_ref['EXT_Matiere'] = "GRAVATS"

    def make_date_key(val):
        d = convertir_date_robuste(val)
        if pd.isna(d): return "NAN_DATE"
        return d.strftime('%Y-%m-%d')

    def make_weight_key(val):
        try:
            v = float(val)
            return "{:.2f}".format(v)
        except:
            return "0.00"

    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    df_ter['Key_Date'] = df_ter['Date_Ref'].apply(make_date_key)
    df_ter['Key_Weight'] = df_ter['Poids_Terrain'].apply(make_weight_key)
    df_ter['Key_Immat'] = df_ter.get('Immatriculation', pd.Series(['']*len(df_ter))).apply(clean_plate)

    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

    df_ref['Key_Date'] = df_ref['Date_Ref'].apply(make_date_key)
    df_ref['Key_Weight'] = df_ref['Poids_Facture'].apply(make_weight_key)
    df_ref['Key_Immat'] = df_ref.get('Immatriculation', pd.Series(['']*len(df_ref))).apply(clean_plate)

    cols_ter = df_ter.columns.tolist()
    cols_ref = df_ref.columns.tolist()

    df_ter['K'] = df_ter['Num Ticket'].replace({'': np.nan, 'ST': np.nan, 'nan': np.nan})
    df_ref['K'] = df_ref['Num Ticket'].replace({'': np.nan, 'ST': np.nan, 'nan': np.nan})

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='inner', suffixes=('_T', '_F'))
    keys_matched = set(m1['K'])
    def get_leftovers(df, key_col, exclude_keys):
        return df[~df[key_col].isin(exclude_keys)].copy()

    match1 = m1.copy()
    match1['Methode'] = '1. Ticket'
    leftover_t1 = get_leftovers(df_ter, 'K', keys_matched)
    leftover_f1 = get_leftovers(df_ref, 'K', keys_matched)

    t2 = leftover_t1[leftover_t1['Key_Immat'] != '']
    f2 = leftover_f1[leftover_f1['Key_Immat'] != '']
    m2 = pd.merge(t2, f2, on=['Key_Date', 'Key_Immat'], how='inner', suffixes=('_T', '_F'))
    match2 = m2.copy()
    match2['Methode'] = '2. Auto (Immat)'
    
    def create_unique_id(df, prefix):
        return [f"{prefix}_{i}" for i in range(len(df))]
        
    leftover_t1['UID'] = create_unique_id(leftover_t1, 'T')
    leftover_f1['UID'] = create_unique_id(leftover_f1, 'F')
    m2_uid = pd.merge(leftover_t1[leftover_t1['Key_Immat'] != ''], leftover_f1[leftover_f1['Key_Immat'] != ''], on=['Key_Date', 'Key_Immat'], how='inner', suffixes=('_T', '_F'))
    ids_t_matched_p2 = set(m2_uid['UID_T']); ids_f_matched_p2 = set(m2_uid['UID_F'])
    leftover_t2 = leftover_t1[~leftover_t1['UID'].isin(ids_t_matched_p2)].copy()
    leftover_f2 = leftover_f1[~leftover_f1['UID'].isin(ids_f_matched_p2)].copy()

    t3 = leftover_t2[leftover_t2['Key_Weight'] != '0.00']
    f3 = leftover_f2[leftover_f2['Key_Weight'] != '0.00']
    m3 = pd.merge(t3, f3, on=['Key_Date', 'Key_Weight'], how='inner', suffixes=('_T', '_F'))
    match3 = m3.copy(); match3['Methode'] = '3. Auto (Poids)'
    
    orph_t = pd.merge(leftover_t2, m3[['Key_Date', 'Key_Weight']], on=['Key_Date', 'Key_Weight'], how='left', indicator=True)
    orph_t = orph_t[orph_t['_merge'] == 'left_only'][cols_ter]; orph_t['Methode'] = 'Non Trouvé (Terrain)'
    orph_f = pd.merge(leftover_f2, m3[['Key_Date', 'Key_Weight']], on=['Key_Date', 'Key_Weight'], how='left', indicator=True)
    orph_f = orph_f[orph_f['_merge'] == 'left_only'][cols_ref]; orph_f['Methode'] = 'Non Trouvé (Facture)'

    final_orph_t = orph_t.rename(columns={c: c + '_T' for c in cols_ter})
    final_orph_f = orph_f.rename(columns={c: c + '_F' for c in cols_ref})
    final = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True)
    
    final['Exutoire'] = "PICHETA"
    def get_col_safe(df, col_name):
        return df[col_name] if col_name in df.columns else pd.Series([np.nan]*len(df), index=df.index)

    t_match_T = get_col_safe(final, 'Num Ticket_T'); t_match_F = get_col_safe(final, 'Num Ticket_F'); t_orph = get_col_safe(final, 'Num Ticket') 
    final['Num Ticket'] = t_match_T.fillna(t_match_F).fillna(t_orph).fillna('')
    d_match_T = get_col_safe(final, 'Date_Ref_T'); d_match_F = get_col_safe(final, 'Date_Ref_F'); d_orph = get_col_safe(final, 'Date_Ref')
    final['Date_Ref'] = d_match_T.fillna(d_match_F).fillna(d_orph).apply(convertir_date_robuste)
    p_T = get_col_safe(final, 'Poids_Terrain_T').fillna(get_col_safe(final, 'Poids_Terrain'))
    p_F = get_col_safe(final, 'Poids_Facture_F').fillna(get_col_safe(final, 'Poids_Facture'))
    final['Poids_Terrain'] = pd.to_numeric(p_T, errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(p_F, errors='coerce').fillna(0)
    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    c_T = get_col_safe(final, 'Client_T').fillna(get_col_safe(final, 'Client'))
    c_F = get_col_safe(final, 'TEMP_CodeAdresse_F').fillna(get_col_safe(final, 'TEMP_CodeAdresse'))
    final['INT Client'] = c_T.fillna(''); final['EXT Client'] = c_F.fillna(''); final['Client'] = "CU GPSO" 
    m_T = get_col_safe(final, 'Matiere_T_T').fillna(get_col_safe(final, 'Matiere_T'))
    final['Matiere_T'] = m_T.fillna('GRAVATS'); final['EXT_Matiere'] = 'GRAVATS' 

    final['Verif_Exutoire'] = np.where((final['Num Ticket_T'].notna()) & (final['Num Ticket_F'].notna()), 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.02).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Verif_Client'] = final.apply(lambda r: "OK" if check_client_compatibility(r, 'INT Client', 'EXT Client') else "Pb.Clt", axis=1)

    if 'Num Bon' in final.columns:
        final['Num Bon'] = final['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    return final

def charger_picheta(f, source):
    temp = pd.read_excel(f, header=None, nrows=20)
    idx = 0
    for i, r in temp.iterrows():
        if "tp manuel" in str(r.values).lower() or "nature" in str(r.values).lower(): idx = i; break
    f.seek(0)
    df = pd.read_excel(f, header=idx)
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
    df = df.rename(columns=cols)
    if "Client" not in df.columns: df["Client"] = f"PICHETA {source}"
    df['Activité'] = source
    return df

# =============================================================================
# 4. MODULE VALENE
# =============================================================================

def charger_valene(f, source):
    try:
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            if "Num Ticket" in str(r.values) or "N° de pesée" in str(r.values): idx = i; break
        f.seek(0); df = pd.read_excel(f, header=idx)
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
             mask_total = (df["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)) & (df["Num Ticket"].isna())
             df = df[~mask_total]
        if "Client" not in df.columns: df["Client"] = f"VALENE {source}"
        df['Activité'] = source
        return df
    except: return pd.DataFrame()

def process_valene(f_pap, f_pav, f_sot, f_exp):
    dfs = []
    if f_pap: dfs.append(charger_valene(f_pap, "PAP"))
    if f_pav: dfs.append(charger_valene(f_pav, "PAV"))
    if f_sot: dfs.append(charger_valene(f_sot, "SOTREMA2"))
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)
    try: df_ref = pd.read_excel(f_exp, sheet_name="RPT_RecherchePeseeDetaillee", header=8)
    except: df_ref = pd.read_excel(f_exp, header=8)
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
    merged['Client'] = restaurer_col(merged, 'Client'); merged['Date_Ref'] = restaurer_col(merged, 'Date_Ref'); merged['Chauffeur'] = restaurer_col(merged, 'Chauffeur'); merged['Immatriculation'] = restaurer_col(merged, 'Immatriculation')
    merged['Exutoire'] = "VALENE"; merged['Poids_Terrain'] = np.floor(pd.to_numeric(merged['Poids_Terrain'], errors='coerce').fillna(0) * 100) / 100; merged['Poids_Facture'] = np.floor(pd.to_numeric(merged['Poids_Facture'], errors='coerce').fillna(0) * 100) / 100; merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']; merged['Date_Ref'] = merged['Date_Ref'].apply(convertir_date_robuste); merged['INT Client'] = merged.get('Client_T', merged.get('Client', '')); merged['EXT Client'] = merged.get('Client_F', ''); merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'}); merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'}); merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
    def verif_client(row):
        c_int = str(row.get('INT Client', '')).upper().strip(); c_ext = str(row.get('EXT Client', '')).upper().strip(); act = str(row.get('Activité', '')).upper()
        if not c_int or not c_ext: return "OK"
        if "SOTREMA2" in act:
            if "GPSO" not in c_int: return "OK"
        if c_int in ["CU GPSO", "CCPIF"] and "CU GRAND PARIS SEINE ET OISE" in c_ext: return "OK"
        if "CU GRAND PARIS SEINE ET OISE" in c_ext and c_int in ["CU GPSO", "CCPIF"]: return "OK"
        if c_int in c_ext or c_ext in c_int: return "OK"
        return "Pb.Clt"
    merged['Verif_Client'] = merged.apply(verif_client, axis=1)
    if 'Date' in merged.columns: merged = merged.drop(columns=['Date'])
    merged = merged.rename(columns={'Date_Ref': 'Date'}); cols_final = ['Date', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
    for c in cols_final:
        if c not in merged.columns: merged[c] = ""
    if 'Num Bon' in merged.columns: merged['Num Bon'] = merged['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    return merged[cols_final]

# =============================================================================
# 5. MODULE SUEZ
# =============================================================================

def charger_suez_terrain(f, type_fichier):
    try:
        temp = pd.read_excel(f, header=None, nrows=10); idx = 3 
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num tp manuel" in row_str or "n°bon de vidage" in row_str: idx = i; break
        
        f.seek(0); df = pd.read_excel(f, header=idx); cols_map = {}
        col_client = None
        
        for c in df.columns:
            cl = str(c).lower().strip()
            if "tp manuel" in cl: cols_map[c] = "Num Ticket"
            elif "bon de vidage" in cl: cols_map[c] = "Num Bon"
            if "quantiteligne" in cl: cols_map[c] = "Poids_Terrain"
            if "description" in cl or "nature" in cl: cols_map[c] = "Matiere_T"
            if "date" in cl: cols_map[c] = "Date_Ref"
            if "immat" in cl or "camion" in cl: cols_map[c] = "Immatriculation"
            
            # Priorité 1: NChantier (Nom chantier)
            if "nchantier" in cl: col_client = c
        
        # Priorité 2: Exutoire (si NChantier non trouvé)
        if not col_client:
            for c in df.columns:
                if "exutoire" in str(c).lower(): col_client = c; break

        if col_client: cols_map[col_client] = "Client"

        df = df.rename(columns=cols_map); df = df.loc[:, ~df.columns.duplicated()]
        
        if 'Num Ticket' in df.columns: 
            df['Num Ticket'] = df['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
        # S'assurer que le Client est propre
        if 'Client' in df.columns:
             df['Client'] = df['Client'].astype(str).replace(['nan', 'None', '', 'NAN'], np.nan)
        
        df['Activité'] = type_fichier; return df
    except Exception as e: st.error(f"Erreur chargement {type_fichier}: {e}"); return pd.DataFrame()

DICT_CORRECTION_SUEZ = {
    "CTC MUREAUX": "CTC LES MUREAUX",
    "DECHETTERIE MLJ CLOSEAUX 1": "DECHETERIE DES CLOSEAUX MANTES LA J",
    "DECHETTERIE MLJ CLOSEAUX 2": "DECHETERIE DES CLOSEAUX MANTES LA J",
    "DECHETTERIE MLV VAUCOULEURS": "DECHETTERIE DE LA VAUCOULEURS"
}

def process_suez(f_ctc, f_dech, f_fac):
    # =========================================================================
    # 1. CHARGEMENT & PREPARATION
    # =========================================================================
    dfs = []
    if f_ctc: dfs.append(charger_suez_terrain(f_ctc, "CTC"))
    if f_dech: dfs.append(charger_suez_terrain(f_dech, "DECH"))
    
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    if 'Poids_Terrain' not in df_ter.columns: df_ter['Poids_Terrain'] = 0
    
    # Chargement Facture
    df_ref = pd.read_excel(f_fac, header=0)

    # FILTRE CLIENT "GPSEOAUB"
    col_target = None
    for c in df_ref.columns:
        if "nom recherche client" in str(c).lower(): col_target = c; break
    if col_target:
        # On ne garde que GPSEOAUB
        df_ref = df_ref[df_ref[col_target].astype(str).str.upper().str.strip() == 'GPSEOAUB']
    
    # Mapping Colonnes Facture
    cols_ref = {}
    col_ext_client_found = False

    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° bon de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "quantité nette" in cl: cols_ref[c] = "Poids_Facture"
        if "humidité" in cl: cols_ref[c] = "Poids_Humidite"
        if "date du bon" in cl: cols_ref[c] = "Date_Ref"
        if "nom recherche client" in cl: cols_ref[c] = "Billing_Client"
        
        # 1. Cible principale : Nom de l'adresse de service (le Site)
        if "ville de l'adresse de service" in cl:
             cols_ref[c] = "EXT Client"
             col_ext_client_found = True
             
        # 2. Cible secondaire : Nom Chantier / Producteur (si pas encore trouvé)
        elif ("chantier" in cl or "producteur" in cl ) and "nom" in cl:
             if not col_ext_client_found:
                 cols_ref[c] = "EXT Client"
                 col_ext_client_found = True
        
        if "description déchet" in cl: cols_ref[c] = "EXT_Matiere"
        if "immatriculation" in cl: cols_ref[c] = "Immatriculation"

    # Fallback : Si on n'a trouvé ni site ni chantier, on prend le payeur (GPSEO)
    if not col_ext_client_found:
        for c in df_ref.columns:
            if "nom recherche client" in str(c).lower():
                cols_ref[c] = "EXT Client"

    df_ref = df_ref.rename(columns=cols_ref)
    df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]
    
    # Nettoyage Types
    if 'Num Ticket' in df_ref.columns: 
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    # Calcul Poids Total = Net + Humidité
    if 'Poids_Facture' in df_ref.columns:
        p_net = pd.to_numeric(df_ref['Poids_Facture'], errors='coerce').fillna(0)
        p_hum = pd.to_numeric(df_ref['Poids_Humidite'], errors='coerce').fillna(0) if 'Poids_Humidite' in df_ref.columns else 0
        df_ref['Poids_Facture'] = (p_net + p_hum) / 1000

    cols_ter = df_ter.columns.tolist()
    cols_ref = df_ref.columns.tolist()

    # =========================================================================
    # PHASE 1 : MATCHING STRICT (TICKET)
    # =========================================================================
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().replace('nan', np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().replace('nan', np.nan)
    
    # On ne fait le match strict que sur les tickets existants
    m1 = pd.merge(df_ter, df_ref, on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'

    # Récupération des orphelins (pour tenter la phase 2)
    left1 = m1[m1['_merge'] == 'left_only'].copy()
    right1 = m1[m1['_merge'] == 'right_only'].copy()

    l_ter = restore_columns(left1, '_T', cols_ter)
    l_ref = restore_columns(right1, '_F', cols_ref)

    # =========================================================================
    # PHASE 2 : SMART MATCH TOLÉRANT (Date + Poids +/- 50kg + Check Client)
    # =========================================================================
    match2 = pd.DataFrame()
    
    # helper de normalisation (Sortie de la boucle pour performance)
    def normalize_site_key(txt):
        if pd.isna(txt): return "NAN"
        t = str(txt).upper().strip()
        
        # Mappings spécifiques (Règles métier)
        if "CTC MLV" in t and "GRAND OUEST" in t: return "BUCHELAY" # Règle explicite 
        
        t = t.replace("MLJ", "MANTES JOLIE").replace("MLV", "MANTES VILLE")
        
        # Tokenization et nettoyage (remplace ponctuation par espace)
        for char in ["-", "_", ".", "/"]:
            t = t.replace(char, " ")
            
        words = t.split()
        stopwords = ["DECHETERIE", "DECHETTERIE", "CTC", "SITE", "SUEZ", "RV", "OSIS", "DES", "LES", "DU", "DE", "LA", "LE", "ET", "COMMUNAUTE", "URBAINE"]
        
        # On garde les mots qui NE SONT PAS des stopwords et > 2 lettres
        tokens = sorted([w for w in words if w not in stopwords and len(w) > 2])
        
        if not tokens: return "EMPTY"
        return " ".join(tokens)

    if not l_ter.empty and not l_ref.empty:
        # Création des clés de jointure
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")

        # Clé de site normalisée
        l_ter['Key_Site'] = l_ter['Client'].apply(normalize_site_key)
        l_ref['Key_Site'] = l_ref['EXT Client'].apply(normalize_site_key)

        # JOINTURE LARGE SUR LA DATE
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        
        if not m_cross.empty:
            # Calcul écart poids
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta_Poids'] = (p_t - p_f).abs()
            
            # FILTRE TOLÉRANCE 
            candidates = m_cross[m_cross['Delta_Poids'] <= 0.1].copy()
            
            # FILTRE CLIENT (Comparaison des clés normalisées)
            # On accepte si les clés sont identiques OU si l'une des deux est vide/NAN/EMPTY
            # (pour ne pas bloquer si info manquante)
            def check_keys(row):
                k1 = row['Key_Site_T']
                k2 = row['Key_Site_F']
                if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return True
                
                # Intersection des mots (plus souple que égalité stricte)
                s1 = set(k1.split())
                s2 = set(k2.split())
                if s1.intersection(s2): return True
                return False

            if not candidates.empty:
                candidates['Client_OK'] = candidates.apply(check_keys, axis=1)
                candidates = candidates[candidates['Client_OK'] == True]
            
            # DÉDOUBLONNAGE
            candidates = candidates.sort_values('Delta_Poids')
            
            # On s'assure qu'un Bon Terrain n'est utilisé qu'une fois
            if 'Num Bon' in candidates.columns:
                match2 = candidates.drop_duplicates(subset=['Num Bon'], keep='first')
            else:
                match2 = candidates.drop_duplicates(subset=['Key_Date', 'Poids_Terrain'], keep='first')

            # On s'assure qu'une ligne Facture n'est utilisée qu'une fois
            if 'Num Ticket_F' in match2.columns:
                match2 = match2.drop_duplicates(subset=['Num Ticket_F'], keep='first')

            if not match2.empty:
                match2['Methode'] = '2. Smart Tolérant'
                match2['_merge'] = 'both'

                # --- DICTATEUR : REMPLACEMENT DU TICKET ---
                # On force le ticket de la facture dans le résultat
                if 'Num Ticket_F' in match2.columns:
                    match2['Num Ticket'] = match2['Num Ticket_F']
                # ------------------------------------------

                # Mise à jour des orphelins finaux
                # On utilise les ID uniques (Bon et Ticket Fac) pour exclure les trouvés
                matched_bons = match2['Num Bon'].tolist() if 'Num Bon' in match2.columns else []
                matched_tickets_fac = match2['Num Ticket_F'].tolist() if 'Num Ticket_F' in match2.columns else []

                final_t = l_ter[~l_ter['Num Bon'].isin(matched_bons)]
                
                if 'Num Ticket' in l_ref.columns:
                    final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_fac)]
                else:
                    final_f = l_ref # Fallback
            else:
                final_t = l_ter
                final_f = l_ref
        else:
            final_t = l_ter
            final_f = l_ref
    else:
        final_t = l_ter
        final_f = l_ref

    # =========================================================================
    # CONSOLIDATION
    # =========================================================================
    
    # Préparez les orphelins (ajout suffixes pour concat)
    final_orph_t = final_t.rename(columns={c: c + '_T' for c in cols_ter})
    final_orph_f = final_f.rename(columns={c: c + '_F' for c in cols_ref})
    
    final_orph_t['_merge'] = 'left_only'
    final_orph_t['Methode'] = 'Non Trouvé'
    final_orph_f['_merge'] = 'right_only'
    final_orph_f['Methode'] = 'Non Trouvé'

    merged = pd.concat([match1, match2, final_orph_t, final_orph_f], ignore_index=True)
    merged['Exutoire'] = "SUEZ"
    
    # --- FONCTION RESOLVE ROBUSTE ---
    def resolve_col(df, col_base):
        # Série de secours (NaN)
        fallback = pd.Series([np.nan] * len(df), index=df.index)
        
        c_t = df.get(f"{col_base}_T", fallback)
        c_f = df.get(f"{col_base}_F", fallback)
        
        # Si la colonne existe déjà (cas Smart Match), on priorise
        if col_base in df.columns:
            return df[col_base].fillna(c_t).fillna(c_f)
        
        return c_t.fillna(c_f)

    # 1. Colonnes vitales
    merged['Num Ticket'] = resolve_col(merged, 'Num Ticket')
    merged['Num Bon'] = resolve_col(merged, 'Num Bon')
    merged['Date'] = resolve_col(merged, 'Date_Ref').apply(convertir_date_robuste)
    merged['Immatriculation'] = resolve_col(merged, 'Immatriculation')

    # 2. Colonnes contextuelles (AJOUTÉ POUR VOIR LES INFOS)
    merged['Chauffeur'] = resolve_col(merged, 'Chauffeur')
    merged['Activité'] = resolve_col(merged, 'Activité')
    merged['Matiere_T'] = resolve_col(merged, 'Matiere_T')
    merged['EXT_Matiere'] = resolve_col(merged, 'EXT_Matiere')
    merged['Dechetterie'] = resolve_col(merged, 'Client')

    # 3. Poids
    p_ter = pd.to_numeric(merged.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    p_ter_t = pd.to_numeric(merged.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    # Si le Smart Match a rempli Poids_Terrain, on le garde, sinon on prend _T
    merged['Poids_Terrain'] = np.where(p_ter > 0, p_ter, p_ter_t)
    
    p_fac = pd.to_numeric(merged.get('Poids_Facture', 0), errors='coerce').fillna(0)
    p_fac_f = pd.to_numeric(merged.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    merged['Poids_Facture'] = np.where(p_fac > 0, p_fac, p_fac_f)
    
    merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']

    # 4. Clients
    # 4. Clients
    merged['INT Client'] = merged['Dechetterie'].fillna("CU GPSO")
    merged['Client'] = "CU GPSO"
    
    # Coalesce robuste (Combine matched + orphans)
    ext_c = merged.get('EXT Client', pd.Series([np.nan]*len(merged)))
    ext_cf = merged.get('EXT Client_F', pd.Series([np.nan]*len(merged)))
    merged['EXT Client'] = ext_c.combine_first(ext_cf).fillna('GPSEOAUB')

    # =========================================================================
    # PATCH "ST" AVEC ALERTE VISUELLE
    # =========================================================================
    def patch_ticket_st(row):
        t = str(row.get('Num Ticket', '')).strip().upper()
        b = str(row.get('Num Bon', '')).strip().upper()
        
        mauvais_tickets = ['ST', 'NAN', '', 'NONE', '0', 'None']
        
        # Si le ticket est pourri MAIS qu'on a un Bon
        if t in mauvais_tickets and b not in mauvais_tickets:
            # On crée un faux numéro unique et visible
            return f"A_CORRIGER_{b}"
            
        return t

    merged['Num Ticket'] = merged.apply(patch_ticket_st, axis=1)

    # =========================================================================
    # KPIs
    # =========================================================================
    merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})
    merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    
    def check_client_suez(row):
        int_c = str(row.get('INT Client', '')).upper().strip()
        ext_c = str(row.get('EXT Client', '')).upper().strip()
        
        # 1. Cas trivial
        if not int_c or not ext_c: return "OK"
        if int_c == ext_c: return "OK"
        
        # 2. Utilisation de la clé normalisée partagée
        k1 = normalize_site_key(int_c)
        k2 = normalize_site_key(ext_c)
        
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        
        # Intersection des tokens normalisés
        s1 = set(k1.split())
        s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        
        # 3. Rattrapage GPSO (si fallback)
        if "GPSO" in int_c and "GPS" in ext_c: return "OK"
        
        return "Pb.Clt"

    merged['Verif_Client'] = merged.apply(check_client_suez, axis=1) 
    merged['Verif_Matiere'] = "OK"

    cols_final = ['Date', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 
                  'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 
                  'Matiere_T', 'Methode', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 
                  'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart', 'Dechetterie']
    
    for c in cols_final:
        if c not in merged.columns: merged[c] = ""
        
    return merged[cols_final]


# =============================================================================
# 6. ADMIN (SOFT DELETE & ARCHIVAGE & MOTIF)
# =============================================================================
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

    status_filter = "FALSE" if voir_archives else "TRUE"
    base_query = f"SELECT * FROM {TABLE_NAME} WHERE \"isActive\" IS {status_filter}"
    if search:
        where_clause = f" AND (\"Num Ticket\" ILIKE '%%{search}%%' OR \"Client\" ILIKE '%%{search}%%' OR \"Num Bon\" ILIKE '%%{search}%%' OR \"Exutoire\" ILIKE '%%{search}%%')"
        query = f"{base_query}{where_clause} ORDER BY id DESC LIMIT {limit}"
    else:
        query = f"{base_query} ORDER BY id DESC LIMIT {limit}"
    
    try:
        df = pd.read_sql(query, engine)
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
                    st.error(f"Erreur SQL : {str(e)}")

    except Exception as e:
        st.error(f"Erreur SQL : {e}")

    st.divider()
    action_label = "♻️ RESTAURER" if voir_archives else "🗑️ ARCHIVER"
    st.subheader(f"Action sur ID : {action_label}")
    c_id, c_motif, c_btn = st.columns([1, 2, 1])
    target_id = c_id.number_input("ID cible", min_value=0, step=1)
    motif_action = c_motif.text_input("Motif de l'action", placeholder="Ex: Doublon, Erreur pesée...")

    if c_btn.button(f"{action_label} la ligne"):
        if target_id > 0:
            new_status = "TRUE" if voir_archives else "FALSE"
            with engine.connect() as conn:
                stmt = text(f"UPDATE {TABLE_NAME} SET \"isActive\" = {new_status}, \"Motif\" = :motif, \"Dernier_Utilisateur\" = :user WHERE id = :id")
                res = conn.execute(stmt, {"id": target_id, "motif": motif_action, "user": st.session_state["username"]})
                conn.commit()
                if res.rowcount > 0:
                    st.success(f"Ligne {target_id} {'restaurée' if voir_archives else 'archivée'} !")
                    st.rerun()
                else:
                    st.warning("ID introuvable.")

# =============================================================================
# 7. DASHBOARD (FILTRES DYNAMIQUES / CASCADE)
# =============================================================================
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

    # 1. CHARGEMENT GLOBAL
    query = f"SELECT * FROM {TABLE_NAME} WHERE \"isActive\" = TRUE ORDER BY \"Date\" DESC"
    df = pd.read_sql(query, engine)
    
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    # Typage
    if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'])
    for c in ['Poids_Terrain', 'Poids_Facture', 'Ecart']: 
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    for c in ['Num Ticket', 'Num Bon']:
        if c in df.columns: df[c] = df[c].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

    # --- BARRE LATÉRALE (DATES) ---
    st.sidebar.divider()
    st.sidebar.subheader("📅 Période")
    min_date = df['Date'].min().date() if not df['Date'].isna().all() else datetime.date.today()
    max_date = df['Date'].max().date() if not df['Date'].isna().all() else datetime.date.today()
    date_range = st.sidebar.date_input("Filtrer par date", [min_date, max_date])

    # Filtrage Date (Base pour la suite)
    if len(date_range) == 2:
        d_start, d_end = date_range
        mask_date = (df['Date'].dt.date >= d_start) & (df['Date'].dt.date <= d_end)
        mask_nat = df['Date'].isna()
        df_filtered_date = df[mask_date | mask_nat]
    else:
        df_filtered_date = df

    # --- FILTRES INTELLIGENTS (EN CASCADE) ---
    with st.expander("🔎 Filtres", expanded=True):
        c_exu, c_tick, c_bon = st.columns(3)
        
        with c_exu:
            exutoires = ["Tous"] + sorted(df_filtered_date['Exutoire'].dropna().unique().tolist())
            choix_exutoire = st.multiselect("1. Exutoire", exutoires, placeholder="Choisir...")

        df_for_lists = df_filtered_date.copy()
        if choix_exutoire and "Tous" not in choix_exutoire:
            df_for_lists = df_for_lists[df_for_lists['Exutoire'].isin(choix_exutoire)]
        
        with c_tick: search_ticket = st.text_input("Num Ticket")
        with c_bon: search_bon = st.text_input("Num Bon")

        c_cli, c_mat, c_act = st.columns(3)
        
        with c_cli:
            clients_dispo = ["Tous"] + sorted(df_for_lists['INT Client'].astype(str).unique().tolist())
            choix_client = st.multiselect("2. Client", clients_dispo, placeholder="Filtrer...")
            
        with c_mat:
            matieres_dispo = ["Tous"] + sorted(df_for_lists['EXT_Matiere'].astype(str).unique().tolist())
            choix_matiere = st.multiselect("3. Matière", matieres_dispo, placeholder="Filtrer...")
            
        with c_act:
            activites_dispo = ["Tous"] + sorted(df_for_lists['Activité'].astype(str).unique().tolist())
            choix_activite = st.multiselect("Activité", activites_dispo, placeholder="Filtrer...")

    # --- APPLICATION FINALE DES FILTRES SUR LE TABLEAU ---
    df_final = df_filtered_date.copy()

    # 1. Filtre Exutoire
    if choix_exutoire and "Tous" not in choix_exutoire:
        df_final = df_final[df_final['Exutoire'].isin(choix_exutoire)]
    
    # 2. Filtre Client
    if choix_client and "Tous" not in choix_client:
        df_final = df_final[df_final['INT Client'].astype(str).isin(choix_client)]
        
    # 3. Filtre Matière
    if choix_matiere and "Tous" not in choix_matiere:
        df_final = df_final[df_final['EXT_Matiere'].astype(str).isin(choix_matiere)]
        
    # 4. Filtre Activité
    if choix_activite and "Tous" not in choix_activite:
        df_final = df_final[df_final['Activité'].astype(str).isin(choix_activite)]

    # 5. Recherche Texte
    if search_ticket:
        df_final = df_final[df_final['Num Ticket'].astype(str).str.contains(search_ticket, case=False, na=False)]
    if search_bon:
        df_final = df_final[df_final['Num Bon'].astype(str).str.contains(search_bon, case=False, na=False)]

    st.divider()

    # DISPLAY
    if 'Verif_Exutoire' in df_final.columns: df_ok_exu = df_final[df_final['Verif_Exutoire'] == 'OK']
    else: df_ok_exu = df_final

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.caption("🏭 Vérif Exutoire")
        if not df_final.empty: st.dataframe(pd.crosstab(df_final['Exutoire'], df_final['Verif_Exutoire'], margins=True, margins_name="Tot"), use_container_width=True)
    with k2:
        st.caption("⚖️ Vérif Tonnes")
        if not df_ok_exu.empty: st.dataframe(pd.crosstab(df_ok_exu['Exutoire'], df_ok_exu['Verif_Tonnes'], margins=True, margins_name="Tot"), use_container_width=True)
    with k3:
        st.caption("🏢 Vérif Client")
        if not df_ok_exu.empty: st.dataframe(pd.crosstab(df_ok_exu['Exutoire'], df_ok_exu['Verif_Client'], margins=True, margins_name="Tot"), use_container_width=True)
    with k4:
        st.caption("♻️ Vérif Matière")
        if not df_ok_exu.empty: st.dataframe(pd.crosstab(df_ok_exu['Exutoire'], df_ok_exu['Verif_Matiere'], margins=True, margins_name="Tot"), use_container_width=True)

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
    if 'Date' in df_disp.columns: df_disp['Date'] = df_disp['Date'].dt.strftime('%d/%m/%y')

    col_cfg = {}
    for col in df_disp.columns:
        if col in ['INT T.', 'EXT T.', 'Ecart']: col_cfg[col] = st.column_config.NumberColumn(col, width="small", format="%.2f")
        else: col_cfg[col] = st.column_config.TextColumn(col, width="small")

    cols_global = ['Date', 'Ticket', 'Bon', 'Exutoire', 'Activ.', 'INT Client', 'EXT Client', 'INT Mat', 'EXT Mat', 'Immat', 'V. Exu', 'V. T.', 'V. Mat', 'V. Cli', 'INT T.', 'EXT T.', 'Ecart']
    cols_tonnage = ['Date', 'Ticket', 'Exutoire', 'Client', 'INT T.', 'EXT T.', 'Ecart', 'V. T.']
    cols_client = ['Date', 'Ticket','Bon', 'Exutoire', 'INT Client', 'EXT Client', 'V. Cli']
    cols_matiere = ['Date', 'Ticket', 'Exutoire', 'INT Mat', 'EXT Mat', 'V. Mat', 'Client']
    cols_exutoire = ['Date', 'Ticket', 'Bon', 'Exutoire', 'Activ.','Client', 'EXT Mat', 'INT Mat', 'EXT T.', 'INT T.']

    def get_safe_cols(column_list, df_target):
        return [c for c in column_list if c in df_target.columns]

    nb_err_exu = len(df_final[df_final['Verif_Exutoire'] != 'OK'])
    df_ok = df_final[df_final['Verif_Exutoire'] == 'OK']
    nb_err_ton = len(df_ok[df_ok['Verif_Tonnes'] != 'OK'])
    nb_err_cli = len(df_ok[df_ok['Verif_Client'] != 'OK'])
    nb_err_mat = len(df_ok[df_ok['Verif_Matiere'] != 'OK'])

    tab1, tab2, tab3, tab4, tab5= st.tabs([
        "🌍 Vue Globale", 
        f"🏭 Exutoire ({nb_err_exu})", 
        f"⚖️ Tonnage ({nb_err_ton})", 
        f"🏢 Client ({nb_err_cli})",
        f"♻️ Matière ({nb_err_mat})"
    ])

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
            return ['background-color: #ffcccc'] * len(row) if is_error else [''] * len(row)

        st.dataframe(df_disp[get_safe_cols(cols_global, df_disp)].style.apply(highlight_rows, axis=1), use_container_width=True, hide_index=True, height=600, column_config=col_cfg)

    with tab2:
        df_err = df_disp[df_disp['V. Exu'] != 'OK']
        if not df_err.empty:
            st.error(f"Il y a {len(df_err)} erreurs d'exutoire.")
            st.dataframe(df_err[get_safe_cols(cols_exutoire, df_err)], use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.success("RAS Exutoire.")

    with tab3:
        mask = (df_disp['V. Exu'] == 'OK') & (df_disp['V. T.'] != 'OK')
        df_err = df_disp[mask]
        if not df_err.empty:
            st.warning(f"Il y a {len(df_err)} écarts de tonnage.")
            st.dataframe(df_err[get_safe_cols(cols_tonnage, df_err)], use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.success("RAS Tonnage.")

    with tab4:
        mask = (df_disp['V. Exu'] == 'OK') & (df_disp['V. Cli'] != 'OK')
        df_err = df_disp[mask]
        if not df_err.empty:
            st.warning(f"Il y a {len(df_err)} erreurs Client.")
            st.dataframe(df_err[get_safe_cols(cols_client, df_err)], use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.success("RAS Client.")

    with tab5:
        mask = (df_disp['V. Exu'] == 'OK') & (df_disp['V. Mat'] != 'OK')
        df_err = df_disp[mask]
        if not df_err.empty:
            st.warning(f"Il y a {len(df_err)} divergences de matière.")
            st.dataframe(df_err[get_safe_cols(cols_matiere, df_err)], use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.success("RAS Matière.")

# =============================================================================
# MAIN APP
# =============================================================================
st.sidebar.title("MENU PRINCIPAL")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login_screen()
else:
    st.sidebar.title(f"👤 {st.session_state['username']}")
    if st.sidebar.button("Se déconnecter"):
        logout()
        
    st.sidebar.divider()
    categorie = st.sidebar.radio("Choisir une section :", ["📊 Analyse & Dashboard", "📥 Import Fichiers", "⚙️ Administration"])
    engine = get_db_engine()

    if categorie == "📊 Analyse & Dashboard":
        interface_dashboard()
        
    elif categorie == "📥 Import Fichiers":
        prestataire = st.sidebar.radio("Prestataire :", ["DUPILLE", "PICHETA", "VALENE", "SUEZ"])
        st.divider()
    
        if prestataire == "DUPILLE":
            st.title("Import DUPILLE")
            c1, c2 = st.columns(2)
            f_lb = c1.file_uploader("Fichier Terrain", type=['xlsx', 'xls', 'xlsm'])
            f_fac = c2.file_uploader("Fichier Facture", type=['xlsx', 'xlsm'])
            if st.button("Lancer") and f_lb and f_fac:
                df = process_dupille(f_lb, f_fac)
                st.dataframe(df)
                if st.checkbox("Enregistrer en Base", value=True): save_to_db(df, engine)

        elif prestataire == "PICHETA":
            st.title("Import PICHETA")
            c1, c2 = st.columns(2)
            with c1:
                f_ctc = st.file_uploader("Fichier CTC", type=['xlsx', 'xls', 'xlsm'])
                f_exp = st.file_uploader("Export Facture", type=['xlsx', 'xls', 'xlsm'])
            with c2:
                f_dech = st.file_uploader("Fichier DECH", type=['xlsx', 'xls', 'xlsm'])
            
            if st.button("Lancer") and f_exp:
                with st.spinner("Matching intelligent en cours..."):
                    df = process_picheta(f_ctc, f_dech, f_exp)
                    def highlight_method(row):
                        m = str(row['Methode'])
                        if 'Auto' in m: return ['background-color: #d4edda; color: #155724'] * len(row) 
                        elif 'Ticket' in m: return [''] * len(row) 
                        else: return ['background-color: #f8d7da; color: #721c24'] * len(row)
                    st.write(f"Résultat : {len(df)} lignes traitées.")
                    cols_view = ['Date_Ref', 'Num Ticket', 'Exutoire', 'Client', 'Methode', 'Verif_Exutoire', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
                    cols_view = [c for c in cols_view if c in df.columns]
                    st.dataframe(df[cols_view].style.apply(highlight_method, axis=1), use_container_width=True)
                    if st.checkbox("Enregistrer en Base", value=True): save_to_db(df, engine)

        elif prestataire == "VALENE":
            st.title("Import VALENE")
            c1, c2, c3 = st.columns(3)
            f_pap = c1.file_uploader("PAP", type=['xlsx', 'xls', 'xlsm'])
            f_pav = c2.file_uploader("PAV", type=['xlsx', 'xls', 'xlsm'])
            f_sot = c3.file_uploader("SOTREMA2", type=['xlsx', 'xls', 'xlsm'])
            f_exp = st.file_uploader("Export Facture", type=['xlsx', 'xls', 'xlsm'])
            if st.button("Lancer") and f_exp:
                df = process_valene(f_pap, f_pav, f_sot, f_exp)
                st.dataframe(df)
                if st.checkbox("Enregistrer en Base", value=True): save_to_db(df, engine)

        elif prestataire == "SUEZ":
            st.title("Import SUEZ")
            start_col, end_col = st.columns(2)
            f_ctc = start_col.file_uploader("Fichier CTC", type=['xlsx', 'xls', 'xlsm'])
            f_dech = end_col.file_uploader("Fichier DECH", type=['xlsx', 'xls', 'xlsm'])
            f_fac = st.file_uploader("Listing GPSEO (Facture)", type=['xlsx', 'xls', 'xlsm'])
            if st.button("Lancer") and f_fac:
                st.session_state['df_suez'] = process_suez(f_ctc, f_dech, f_fac)

            if 'df_suez' in st.session_state:
                df = st.session_state['df_suez']
                
                with st.expander("🔍 Filtres", expanded=True):
                    c1, c2 = st.columns(2)
                    opts_dech = ["Tous"] + sorted(df['Dechetterie'].dropna().astype(str).unique().tolist())
                    sel_dech = c1.multiselect("Déchetterie", opts_dech, default="Tous")
                    
                    # Cascade: Si on a choisi des déchetteries, on ne montre que les flux dispos pour celles-ci
                    df_flux_source = df.copy()
                    if sel_dech and "Tous" not in sel_dech:
                        df_flux_source = df_flux_source[df_flux_source['Dechetterie'].astype(str).isin(sel_dech)]
                    
                    opts_flux = ["Tous"] + sorted(df_flux_source['Matiere_T'].dropna().astype(str).unique().tolist())
                    sel_flux = c2.multiselect("Flux (Matière)", opts_flux, default="Tous")

                df_view = df.copy()
                if sel_dech and "Tous" not in sel_dech:
                    df_view = df_view[df_view['Dechetterie'].astype(str).isin(sel_dech)]
                if sel_flux and "Tous" not in sel_flux:
                    df_view = df_view[df_view['Matiere_T'].astype(str).isin(sel_flux)]
                
                st.caption(f"Lignes affichées : {len(df_view)} / {len(df)}")
                st.dataframe(df_view)
                
                if st.button("💾 Enregistrer tout en Base", type="primary"): 
                    save_to_db(df, engine)
                    st.success("Données enregistrées avec succès !")

    elif categorie == "⚙️ Administration":
        interface_admin()