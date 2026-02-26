import pandas as pd
import numpy as np
import logging
import streamlit as st
import re
import unicodedata
from datetime import datetime

# --- LOGGER ---
logger = logging.getLogger(__name__)

# --- UTILS (Copied or imported if possible) ---
def convertir_date_robuste(val):
    """Imported from main app logic if possible, otherwise fallback"""
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (datetime, pd.Timestamp)): return val
    s = str(val).strip()
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]:
        try: return datetime.strptime(s, fmt)
        except: continue
    return pd.to_datetime(val, errors='coerce')

def normalize_site_key(txt):
    if not txt or pd.isna(txt): return "NAN"
    t = str(txt).lower()
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'[^a-z0-9]', ' ', t)
    return " ".join(t.split())

def normaliser_matiere_valene(m):
    if not m or pd.isna(m): return ""
    s = str(m).upper().strip()
    if "PAPIER" in s or "CARTON" in s: return "PAPIERS/CARTONS"
    if "EMBALLAGE" in s or "PAV" in s: return "EMBALLAGES"
    if "SOTREMA" in s: return "MENAGERS"
    return s

def normaliser_matiere_picheta_valoseine(m):
    if not m or pd.isna(m): return ""
    s = str(m).upper().strip()
    if "GRAVATS" in s: return "GRAVATS"
    if "DECHETS VERTS" in s or "VERTS" in s: return "DECHETS VERTS"
    if "BOIS" in s: return "BOIS"
    if "TOUT VENANT" in s or "ENCOMBRANTS" in s: return "TOUT VENANT"
    return s

def resolve_col(df, base_name):
    """Helper to find a column even if it was renamed with _T or _F suffixes"""
    if base_name in df.columns: return df[base_name]
    ct, cf = f"{base_name}_T", f"{base_name}_F"
    if ct in df.columns and cf in df.columns:
        return df[ct].fillna(df[cf])
    if ct in df.columns: return df[ct]
    if cf in df.columns: return df[cf]
    return pd.Series([np.nan]*len(df))

def clean_client_match(c):
    if not c or pd.isna(c): return ""
    return str(c).strip().upper()

# --- PROVIDER: VALENE ---

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

# --- PROVIDER: VALOSEINE ---

def charger_valoseine(f):
    try:
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
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Valoseine: {e}")
        return pd.DataFrame()

def process_valoseine(f_ter, f_fac):
    logger.info("Début traitement PICHETA VALOSEINE")
    
    df_ter = charger_valoseine(f_ter)
    if df_ter.empty: return pd.DataFrame()

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
        df_ref['EXT_Matiere'] = "GRAVATS"

    if 'Matiere_T' in df_ter.columns:
        df_ter['Matiere_T'] = df_ter['Matiere_T'].apply(normaliser_matiere_picheta_valoseine)
    if 'EXT_Matiere' in df_ref.columns:
        df_ref['EXT_Matiere'] = df_ref['EXT_Matiere'].apply(normaliser_matiere_picheta_valoseine)
    
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        mask_garbage = df_ref['Num Ticket'].astype(str).str.contains("Libellé|source|Code produ|Total", case=False, na=False)
        df_ref = df_ref[~mask_garbage]
        if 'Date_Ref' in df_ref.columns:
             df_ref = df_ref.dropna(subset=['Date_Ref'])
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

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'

    matched_ids_t = match1['K'].unique()
    matched_ids_f = match1['K'].unique()
    l_ter = df_ter[~df_ter['K'].isin(matched_ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(matched_ids_f)].copy()

    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN")
        l_ter_valid = l_ter[l_ter['Key_Date'] != "NAN"].copy()
        l_ref_valid = l_ref[l_ref['Key_Date'] != "NAN"].copy()

        if not l_ter_valid.empty and not l_ref_valid.empty:
            m_cross = pd.merge(l_ter_valid, l_ref_valid, on='Key_Date', how='inner', suffixes=('_T', '_F'))
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
                    match2['Methode'] = '2. Smart Match'; match2['_merge'] = 'both'
                    matched_uids_ter = (match2['Key_Date'].astype(str) + "_" + match2['Poids_Terrain'].astype(str)).tolist()
                    l_ter['_UID'] = l_ter['Key_Date'].astype(str) + "_" + l_ter['Poids_Terrain'].astype(str)
                    final_t = l_ter[~l_ter['_UID'].isin(matched_uids_ter)].drop(columns=['_UID'])
                    if 'Num Ticket_F' in match2.columns:
                        matched_tickets = match2['Num Ticket_F'].tolist()
                        final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets)]
                    else: final_f = l_ref
                else: final_t, final_f = l_ter, l_ref
        else: final_t, final_f = l_ter, l_ref
    else: final_t, final_f = l_ter, l_ref

    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'], errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'], errors='coerce')
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
                 if 'Num Bon' in candidates_3.columns: match3 = candidates_3.drop_duplicates(subset=['Num Bon'], keep='first')
                 else: match3 = candidates_3.drop_duplicates(subset=['Date_Ref_T', 'Poids_Terrain'], keep='first')
                 match3['Methode'] = '3. Match Flex Date'; match3['_merge'] = 'both'; match3['Date_Ref'] = match3['Date_Ref_T']
                 matched_uids_t = (match3['Num Ticket_T'].apply(str) + match3['Poids_Terrain'].apply(str)).tolist()
                 final_t['_UID'] = final_t['Num Ticket'].apply(str) + final_t['Poids_Terrain'].apply(str)
                 final_t = final_t[~final_t['_UID'].isin(matched_uids_t)].drop(columns=['_UID'])
         if 'Date_Obj' in final_t.columns: final_t = final_t.drop(columns=['Date_Obj'])
         if 'Date_Obj' in final_f.columns: final_f = final_f.drop(columns=['Date_Obj'])

    cols_ter_orig = df_ter.columns
    cols_ref_orig = df_ref.columns
    final_orph_t = final_t.rename(columns={c: c + '_T' for c in cols_ter_orig})
    final_orph_f = final_f.rename(columns={c: c + '_F' for c in cols_ref_orig})
    final_orph_t['_merge'] = 'left_only'; final_orph_t['Methode'] = 'Non Trouvé'
    final_orph_f['_merge'] = 'right_only'; final_orph_f['Methode'] = 'Non Trouvé'

    final = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True)
    final['Exutoire'] = "PICHETA VALOSEINE DECH TRIEL"
    
    if 'Num Ticket_F' in final.columns:
        final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    else:
        final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str)
    final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
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
        if row['_merge'] != 'both': return "OK"
        mt = str(row.get('Matiere_T', '')).upper(); mf = str(row.get('EXT_Matiere', '')).upper()
        if mt == mf or mt in mf or mf in mt: return "OK"
        return "Pb.Mat"
    final['Verif_Matiere'] = final.apply(check_mat, axis=1)
    final['Activité'] = resolve_col(final, 'Activité').fillna("DECH")

    def check_client_picheta(row):
        int_c = str(row.get('INT Client', '')).upper().strip(); ext_c = str(row.get('EXT Client', '')).upper().strip()
        if not int_c or not ext_c: return "OK"
        if "TRIEL" in int_c and "TRIEL" in ext_c: return "OK"
        if int_c == ext_c: return "OK"
        k1 = normalize_site_key(int_c); k2 = normalize_site_key(ext_c)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        return "Pb.Clt"
    final['Verif_Client'] = final.apply(check_client_picheta, axis=1)
    return final
