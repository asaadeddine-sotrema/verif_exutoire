import pandas as pd
import numpy as np
import logging
from datetime import datetime
import re
import unicodedata

# --- LOGGER ---
logger = logging.getLogger(__name__)

# --- UTILS ---

def convertir_date_robuste(val):
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (datetime, pd.Timestamp)): return val
    s = str(val).strip()
    
    # FORMATS ISO
    if len(s) >= 10 and s[4] == '-' and s[7] == '-' and s[0:4].isdigit():
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except:
            pass

    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"]:
        try: return datetime.strptime(s, fmt)
        except: continue
    return pd.to_datetime(val, dayfirst=True, errors='coerce')

def normalize_site_key(txt):
    if not txt or pd.isna(txt): return "NAN"
    t = str(txt).lower()
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'[^a-z0-9]', ' ', t)
    return " ".join(t.split())

def resolve_col(df, base_name):
    if base_name in df.columns: return df[base_name]
    ct, cf = f"{base_name}_T", f"{base_name}_F"
    if ct in df.columns and cf in df.columns:
        return df[ct].fillna(df[cf])
    if ct in df.columns: return df[ct]
    if cf in df.columns: return df[cf]
    return pd.Series([np.nan]*len(df))

# --- PROVIDER: SATEL SMIRTOM ENC ---

def charger_satel_smirtom_enc(file_path):
    try:
        # Load first 20 rows to find header
        temp = pd.read_excel(file_path, header=None, nrows=20)
        best_idx = 0
        for i, row in temp.iterrows():
            r_str = row.astype(str).str.lower().tolist()
            if "date" in r_str and ("chauffeur" in r_str or "immatriculation" in r_str):
                best_idx = i
                break
                
        if hasattr(file_path, 'seek'):
            file_path.seek(0)
            
        df = pd.read_excel(file_path, header=best_idx)
        
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num bon" in cl: cols[c] = "Num Bon"
            elif "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "tonnage" in cl or "poids" in cl: cols[c] = "Poids_Terrain"
            elif "description" in cl or "matière" in cl or "matiere" in cl: cols[c] = "Matiere_T"
            elif "date" in cl: cols[c] = "Date_Ref"
            elif "nchantier" in cl or "client" in cl: cols[c] = "Client"
            elif "immatriculation" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            elif "exutoire" in cl or "transporteur" in cl: cols[c] = "Transporteur"
            
        df = df.rename(columns=cols)
        
        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce').fillna(0)
        else:
            df["Poids_Terrain"] = 0
            
        if 'Date_Ref' in df.columns:
             df['Date_Ref'] = pd.to_datetime(df['Date_Ref'], errors='coerce').dt.date
             
        df = df.dropna(subset=['Date_Ref', 'Num Ticket'], how='all')
        df['Activité'] = "ENCOMBRANTS"
        return df
    except Exception as e:
        logger.error(f"Erreur chargement SATEL SMIRTOM ENC: {e}"); return pd.DataFrame()


def process_satel_smirtom_enc(f_ter, f_fac):
    logger.info("Début traitement SATEL SMIRTOM ENC")
    df_ter = charger_satel_smirtom_enc(f_ter)
    if df_ter.empty: return pd.DataFrame()
    df_ref_raw = pd.read_excel(f_fac, header=None, dtype=str)
    header_row_idx = None
    for i, row in df_ref_raw.iterrows():
        r_str = row.astype(str).str.lower().tolist()
        if any("num bon" in s for s in r_str) and any("nomclient" in s for s in r_str):
            header_row_idx = i; break
    if header_row_idx is not None:
        df_ref = df_ref_raw.iloc[header_row_idx+1:].copy()
        df_ref.columns = df_ref_raw.iloc[header_row_idx]; df_ref.columns = df_ref.columns.astype(str)
        new_cols = []; seen = {}
        for c in df_ref.columns:
            c_str = str(c).strip()
            if c_str in seen: seen[c_str] += 1; new_cols.append(f"{c_str}.{seen[c_str]}")
            else: seen[c_str] = 0; new_cols.append(c_str)
        df_ref.columns = new_cols
    else: df_ref = df_ref_raw
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "num bon" in cl: cols_ref[c] = "Num Ticket"
        if "quantiteligne" in cl: cols_ref[c] = "Poids_Facture"
        if "immatriculation" in cl: cols_ref[c] = "Immatriculation"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "nomclient" in cl: cols_ref[c] = "EXT Client"
        if "description" in cl: cols_ref[c] = "EXT_Matiere"
    df_ref = df_ref.rename(columns=cols_ref)
    if "Poids_Facture" in df_ref.columns: df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
    if 'Date_Ref' in df_ref.columns: df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date
    if 'Num Ticket' in df_ter.columns: df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'
    ids_t = match1['K'].unique(); ids_f = match1['K'].unique()
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy(); l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        m2 = pd.merge(l_ter[l_ter['Key_Date'] != "NAN"], l_ref[l_ref['Key_Date'] != "NAN"], on='Key_Date', suffixes=('_T', '_F'))
        if not m2.empty:
            m2['Delta'] = abs(pd.to_numeric(m2['Poids_Terrain'], errors='coerce') - pd.to_numeric(m2['Poids_Facture'], errors='coerce'))
            cands = m2[m2['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first'); match2['Methode'] = '2. Rapprochement Intelligent'; match2['_merge'] = 'both'
                matched_tickets_f = match2['Num Ticket_F'].tolist(); l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str); l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str); uids = match2['UID_T'].unique()
                l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T']); match2 = match2.drop(columns=['UID_T'])

    orph_t = l_ter.rename(columns={c: c + '_T' for c in df_ter.columns}); orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    orph_f = l_ref.rename(columns={c: c + '_F' for c in df_ref.columns}); orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    if 'Num Ticket_F' in final.columns: final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else: final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
    
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str)
    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Poids_Terrain'] = pd.to_numeric(resolve_col(final, 'Poids_Terrain'), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(resolve_col(final, 'Poids_Facture'), errors='coerce').fillna(0); final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    final['INT Client'] = final.get('Client_T', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    final['EXT Client'] = final.get('EXT Client', pd.Series(np.nan, index=final.index)).fillna('').astype(str)
    final['Activité'] = "ENCOMBRANTS"; final['Exutoire'] = "SATEL SMIRTOM ENC"
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    def check_cl(row):
        i = str(row.get('INT Client','')).upper().strip(); e = str(row.get('EXT Client','')).upper().strip()
        if not i or not e: return "OK"
        if i == e or normalize_site_key(i) == normalize_site_key(e): return "OK"
        k1 = normalize_site_key(i); k2 = normalize_site_key(e)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        return "Pb.Clt"
    final['Verif_Client'] = final.apply(check_cl, axis=1)
    return final
