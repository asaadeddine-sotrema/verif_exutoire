import pandas as pd
import numpy as np
import logging
import streamlit as st
import re

logger = logging.getLogger(__name__)

# Note: These helpers are expected to be available from the main app or other modules
# Since they are shared, we might need to import them or define them if they are simple.
# For now, we'll import them from app if possible, or assume they are passed/defined.

try:
    from app import convertir_date_robuste, normalize_site_key, resolve_col, clean_client_match, check_client_compatibility
except ImportError:
    # Fallbacks if app is not importable (e.g. during script execution)
    def convertir_date_robuste(val):
        return pd.to_datetime(val, errors='coerce')
    def normalize_site_key(val):
        return str(val).upper().strip()
    def resolve_col(df, col):
        return df.get(col, pd.Series([np.nan]*len(df)))
    def clean_client_match(val):
        return str(val).strip()
    def check_client_compatibility(row, col1, col2):
        return True

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
    df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
    return df

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
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
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
    cols_ref_list = df_ref.columns

    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'
    matched_ids_t = match1['K'].unique()
    l_ter = df_ter[~df_ter['K'].isin(matched_ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(matched_ids_t)].copy()

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
            candidates = candidates.sort_values('Delta_Poids')
            if 'Num Bon' in candidates.columns:
                match2 = candidates.drop_duplicates(subset=['Num Bon'], keep='first')
            else:
                match2 = candidates.drop_duplicates(subset=['Key_Date', 'Poids_Terrain'], keep='first')
            if not match2.empty:
                match2['Methode'] = '2. Smart Match'; match2['_merge'] = 'both'
                if 'Num Ticket_F' in match2.columns: match2['Num Ticket'] = match2['Num Ticket_F']
                matched_tickets_fac = match2['Num Ticket_F'].tolist() if 'Num Ticket_F' in match2.columns else []
                match2['_UID_EXCL'] = match2['Key_Date'].astype(str) + "_" + match2['Poids_Terrain'].astype(str)
                l_ter['_UID_EXCL'] = l_ter['Key_Date'].astype(str) + "_" + l_ter['Poids_Terrain'].astype(str)
                matched_uids_ter = match2['_UID_EXCL'].tolist()
                final_t = l_ter[~l_ter['_UID_EXCL'].isin(matched_uids_ter)]
                if 'Num Ticket' in l_ref.columns: final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_fac)]
                else: final_f = l_ref
            else: final_t, final_f = l_ter, l_ref
        else: final_t, final_f = l_ter, l_ref
    else: final_t, final_f = l_ter, l_ref

    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         offset_dfs = []
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'], errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'], errors='coerce')
         f_t_clean = final_t.dropna(subset=['Date_Obj']).copy()
         f_f_clean = final_f.dropna(subset=['Date_Obj']).copy()
         if not f_t_clean.empty and not f_f_clean.empty:
             for offset in range(-3, 4):
                 temp = f_t_clean.copy()
                 temp['Join_Date'] = temp['Date_Obj'] + pd.Timedelta(days=offset); temp['_Offset'] = offset
                 offset_dfs.append(temp)
             t_expanded = pd.concat(offset_dfs)
             m_flex = pd.merge(t_expanded, f_f_clean, left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
             if not m_flex.empty:
                 m_flex['Delta_Poids'] = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs()
                 m_flex['Delta_Days'] = m_flex['_Offset'].abs()
                 candidates_3 = m_flex[m_flex['Delta_Poids'] <= 0.5].copy()
                 if not candidates_3.empty:
                     candidates_3 = candidates_3.sort_values(['Delta_Days', 'Delta_Poids'])
                     if 'Num Bon' in candidates_3.columns: match3 = candidates_3.drop_duplicates(subset=['Num Bon'], keep='first')
                     else: match3 = candidates_3.drop_duplicates(subset=['Date_Ref_T', 'Poids_Terrain'], keep='first')
                     if not match3.empty:
                         match3['Methode'] = '3. Match Flex Date'; match3['_merge'] = 'both'; match3['Date_Ref'] = match3['Date_Ref_T']
                         if 'Num Ticket_F' in match3.columns: match3['Num Ticket'] = match3['Num Ticket_F']
                         def make_uid(df, s): return df[f'Num Ticket{s}'].astype(str) + "_" + df[f'Poids_Terrain{"" if s=="_T" else ""}'].astype(str) + "_" + df[f'Date_Ref{s}'].astype(str)
                         matched_uids_t = make_uid(match3, '_T').tolist(); matched_uids_f = make_uid(match3, '_F').tolist()
                         final_t['_UID_CLEAN'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str) + "_" + final_t['Date_Ref'].astype(str)
                         final_f['_UID_CLEAN'] = final_f['Num Ticket'].astype(str) + "_" + final_f['Poids_Facture'].astype(str) + "_" + final_f['Date_Ref'].astype(str)
                         final_t = final_t[~final_t['_UID_CLEAN'].isin(matched_uids_t)].drop(columns=['_UID_CLEAN'])
                         final_f = final_f[~final_f['_UID_CLEAN'].isin(matched_uids_f)].drop(columns=['_UID_CLEAN'])
                         for c in ['Date_Obj_T', 'Date_Obj_F', 'Join_Date', '_Offset', 'Delta_Days', 'Delta_Poids']: 
                             if c in match3.columns: match3 = match3.drop(columns=[c])
         if 'Date_Obj' in final_t.columns: final_t = final_t.drop(columns=['Date_Obj'])
         if 'Date_Obj' in final_f.columns: final_f = final_f.drop(columns=['Date_Obj'])

    final_orph_t = final_t.rename(columns={c: c + '_T' for c in cols_ter})
    final_orph_f = final_f.rename(columns={c: c + '_F' for c in cols_ref_list})
    final_orph_t['_merge'] = 'left_only'; final_orph_t['Methode'] = 'Non Trouvé'
    final_orph_f['_merge'] = 'right_only'; final_orph_f['Methode'] = 'Non Trouvé'

    final = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True)
    final['Exutoire'] = "PICHETA GPSEO"

    if 'Num Ticket_F' in final.columns and 'Num Ticket_T' in final.columns:
         t_smart = final['Num Ticket'] if 'Num Ticket' in final.columns else np.nan
         final['Num Ticket'] = t_smart.fillna(final['Num Ticket_F']).fillna(final['Num Ticket_T']).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    else: final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    
    final['Num Ticket'] = final['Num Ticket'].astype(str).replace(r'(?i)^\s*ST\s*$', np.nan, regex=True).fillna('ST')
    c_nb = final.get('Num Bon', pd.Series([np.nan]*len(final)))
    c_nb_t = final.get('Num Bon_T', pd.Series([np.nan]*len(final)))
    c_nb_f = final.get('Num Bon_F', pd.Series([np.nan]*len(final)))
    final['Num Bon'] = c_nb.fillna(c_nb_t).fillna(c_nb_f).astype(str).replace(['nan', 'NAN', 'None'], '')
    final['Date_Ref'] = resolve_col(final, 'Date_Ref')
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    
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
    final['INT Client'] = resolve_col(final, 'Client').fillna("GPSEO").astype(str).replace(['nan', 'NAN', 'None'], '') 
    final['Client'] = "GPSEO"
    c_F_clean = final.get('Client_F', final.get('TEMP_CodeAdresse_F', pd.Series([np.nan]*len(final))))
    final['EXT Client'] = c_F_clean.fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    final['Matiere_T'] = resolve_col(final, 'Matiere_T').fillna('GRAVATS')
    final['EXT_Matiere'] = 'GRAVATS'
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"
    final['Verif_Client'] = final.apply(lambda r: "OK" if check_client_compatibility(r, 'INT Client', 'EXT Client') else "Pb.Clt", axis=1)
    if 'Num Bon' in final.columns: final['Num Bon'] = final['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    return final

def charger_picheta_smirtom(f, source_name="PICHETA SMIRTOM"):
    try:
        temp = pd.read_excel(f, header=None, nrows=20); idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "n°bon de vidage" in row_str or "num tp manuel" in row_str: idx = i; break
        f.seek(0); df = pd.read_excel(f, header=idx, dtype=str)
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "n°bon de vidage" in cl: cols[c] = "Num Bon"
            elif "tonnages" in cl: cols[c] = "Poids_Terrain"
            elif "date" in cl and "vidage" not in cl: cols[c] = "Date_Ref"
            elif "exutoire" in cl: cols[c] = "Exutoire"
            elif "immat" in cl or "camion" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "nature" in cl: cols[c] = "Matiere_T"
        df = df.rename(columns=cols)
        if "Poids_Terrain" in df.columns: df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
        df['Activité'] = source_name; df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Picheta Smirtom ({source_name}): {e}"); return pd.DataFrame()

def process_picheta_smirtom(f_ter, f_fac):
    logger.info("Début traitement PICHETA SMIRTOM"); df_ter = charger_picheta_smirtom(f_ter, "DECH")
    if df_ter.empty: return pd.DataFrame()
    temp = pd.read_excel(f_fac, header=None, nrows=30); idx_inv = 0
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        if "n° document" in row_str and "q liv" in row_str: idx_inv = i; break
    f_fac.seek(0); df_ref = pd.read_excel(f_fac, header=idx_inv, dtype=str)
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° document" in cl: cols_ref[c] = "Num Ticket"
        if "q liv" in cl: cols_ref[c] = "Poids_Facture"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "chantier" in cl: cols_ref[c] = "Client"
        if "libellé produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
    df_ref = df_ref.rename(columns=cols_ref)
    if "Poids_Facture" in df_ref.columns: df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
    if 'TEMP_CodeAdresse' in df_ref.columns: df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETTERIE PICHETA SMIRTOM')
    else: df_ref['Client'] = "DECHETTERIE PICHETA SMIRTOM"
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)
    if 'Num Ticket' in df_ref.columns: df_ref = df_ref[~df_ref['Num Ticket'].astype(str).str.contains("Libellé interne", na=False)]
    if 'Num Ticket' in df_ter.columns: df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'
    ids_t = match1['K'].unique(); l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy(); l_ref = df_ref[~df_ref['K'].isin(ids_t)].copy()
    
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else "NAN")
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0); p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs(); cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first'); match2['Methode'] = '2. Smart Match'; match2['_merge'] = 'both'
                 matched_tickets_f = match2['Num Ticket_F'].tolist(); match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str) + "_" + match2['Num Ticket_T'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str) + "_" + l_ter['Num Ticket'].astype(str)
                 uids_done = match2['UID_T'].unique(); final_t = l_ter[~l_ter['UID_T'].isin(uids_done)].drop(columns=['UID_T'])
                 final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
            else: final_t, final_f = l_ter, l_ref
        else: final_t, final_f = l_ter, l_ref
    else: final_t, final_f = l_ter, l_ref

    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref']); final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'])
         dfs_off = []
         for off in range(-3, 4):
             tmp = final_t.dropna(subset=['Date_Obj']).copy(); tmp['Join_Date'] = tmp['Date_Obj'] + pd.Timedelta(days=off); dfs_off.append(tmp)
         t_exp = pd.concat(dfs_off); m_flex = pd.merge(t_exp, final_f.dropna(subset=['Date_Obj']), left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
         if not m_flex.empty:
             diff = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs(); cands3 = m_flex[diff <= 0.05].sort_values('Poids_Terrain')
             if not cands3.empty:
                 match3 = cands3.drop_duplicates(subset=['Num Ticket_F'], keep='first'); match3['Methode'] = '3. Flex Match'; match3['_merge'] = 'both'; match3['Date_Ref'] = match3['Date_Ref_T']
                 matched_tf = match3['Num Ticket_F'].tolist(); match3['UID_T'] = match3['Num Ticket_T'].astype(str) + "_" + match3['Poids_Terrain'].astype(str)
                 final_t['UID_T'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str)
                 uids3 = match3['UID_T'].unique(); final_t = final_t[~final_t['UID_T'].isin(uids3)]; final_f = final_f[~final_f['Num Ticket'].isin(matched_tf)]
                 
    cols_t = df_ter.columns; cols_f = df_ref.columns
    orph_t = final_t.rename(columns={c: c + '_T' for c in cols_t}); orph_f = final_f.rename(columns={c: c + '_F' for c in cols_f})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'; orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    final = pd.concat([match1, match2, match3, orph_t, orph_f], ignore_index=True); final['Exutoire'] = "PICHETA SMIRTOM"
    
    if 'Num Ticket_F' in final.columns: final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else: final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str); final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str)
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0); final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0); final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)
    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']; final['INT Client'] = final.get('Client_T', final.get('Client')).fillna("SMIRTOM").astype(str); final['EXT Client'] = final.get('Client_F').fillna("").astype(str)
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext'); final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"; final['Activité'] = resolve_col(final, 'Activité').fillna("DECH")
    
    def check_client_picheta(row):
        int_c = str(row.get('INT Client', '')).upper().strip(); ext_c = str(row.get('EXT Client', '')).upper().strip()
        if not int_c or not ext_c: return "OK"
        if int_c == ext_c: return "OK"
        k1 = normalize_site_key(int_c); k2 = normalize_site_key(ext_c)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        return "OK" if s1.intersection(s2) else "Pb.Clt"

    final['Verif_Client'] = final.apply(check_client_picheta, axis=1)
    return final

def charger_picheta_inoe(f, source_name="PICHETA INOE"):
    try:
        temp = pd.read_excel(f, header=None, nrows=20); idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num tp manuel" in row_str and "num bon" in row_str: idx = i; break
            if "date" in row_str and "exutoire" in row_str: idx = i; break
        f.seek(0); df = pd.read_excel(f, header=idx, dtype=str); cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num tp manuel" in cl: cols[c] = "Num Ticket"
            elif "num bon" in cl or "n°bon" in cl: cols[c] = "Num Bon"
            elif "quantiteligne" in cl: cols[c] = "Poids_Terrain"
            elif "date" in cl and "vidage" not in cl: cols[c] = "Date_Ref"
            elif "exutoire" in cl: cols[c] = "Exutoire"
            elif "immat" in cl or "camion" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "description" in cl or "nature" in cl: cols[c] = "Matiere_T"
        df = df.rename(columns=cols)
        if "Poids_Terrain" in df.columns: df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
        df['Activité'] = source_name; df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        return df
    except Exception as e:
        logger.error(f"Erreur chargement Picheta Inoe ({source_name}): {e}"); return pd.DataFrame()

def process_picheta_inoe(f_ctc, f_dech, f_inv):
    logger.info("Début traitement PICHETA INOE"); dfs = []
    if f_ctc: dfs.append(charger_picheta_inoe(f_ctc, "CTC"))
    if f_dech: dfs.append(charger_picheta_inoe(f_dech, "DECH"))
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    temp = pd.read_excel(f_inv, header=None, nrows=30); idx_inv = 0
    for i, r in temp.iterrows():
        row_str = str(r.values).lower()
        if "n° du bl" in row_str and "quantité" in row_str: idx_inv = i; break
    f_inv.seek(0); df_ref = pd.read_excel(f_inv, header=idx_inv, dtype=str)
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° du bl" in cl: cols_ref[c] = "Num Ticket"
        if "quantité" in cl: cols_ref[c] = "Poids_Facture"
        if "date" in cl: cols_ref[c] = "Date_Ref"
        if "client" in cl or "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
        if "produit" in cl: cols_ref[c] = "EXT_Matiere"
    df_ref = df_ref.rename(columns=cols_ref)
    if "Poids_Facture" in df_ref.columns: df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
    df_ref['Client'] = df_ref['TEMP_CodeAdresse'].apply(clean_client_match).replace('', 'DECHETTERIE PICHETA INOE') if 'TEMP_CodeAdresse' in df_ref.columns else "DECHETTERIE PICHETA INOE"
    df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)
    if 'Num Ticket' in df_ter.columns: df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'
    ids_t = match1['K'].unique(); l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy(); l_ref = df_ref[~df_ref['K'].isin(ids_t)].copy()
    
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else "NAN")
        m_cross = pd.merge(l_ter, l_ref, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0); p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta'] = (p_t - p_f).abs(); cands = m_cross[m_cross['Delta'] <= 0.05].sort_values('Delta')
            if not cands.empty:
                 match2 = cands.drop_duplicates(subset=['Num Ticket_F'], keep='first'); match2['Methode'] = '2. Smart Match'; match2['_merge'] = 'both'
                 matched_tickets_f = match2['Num Ticket_F'].tolist(); match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str) + "_" + match2['Num Ticket_T'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str) + "_" + l_ter['Num Ticket'].astype(str)
                 uids_done = match2['UID_T'].unique(); final_t = l_ter[~l_ter['UID_T'].isin(uids_done)].drop(columns=['UID_T'])
                 final_f = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
            else: final_t, final_f = l_ter, l_ref
        else: final_t, final_f = l_ter, l_ref
    else: final_t, final_f = l_ter, l_ref

    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref']); final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'])
         dfs_off = []
         for off in range(-3, 4):
             tmp = final_t.dropna(subset=['Date_Obj']).copy(); tmp['Join_Date'] = tmp['Date_Obj'] + pd.Timedelta(days=off); dfs_off.append(tmp)
         t_exp = pd.concat(dfs_off); m_flex = pd.merge(t_exp, final_f.dropna(subset=['Date_Obj']), left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
         if not m_flex.empty:
             diff = (m_flex['Poids_Terrain'] - m_flex['Poids_Facture']).abs(); cands3 = m_flex[diff <= 0.05].sort_values('Poids_Terrain')
             if not cands3.empty:
                 match3 = cands3.drop_duplicates(subset=['Num Ticket_F'], keep='first'); match3['Methode'] = '3. Flex Match'; match3['_merge'] = 'both'; match3['Date_Ref'] = match3['Date_Ref_T']
                 matched_tf = match3['Num Ticket_F'].tolist(); match3['UID_T'] = match3['Num Ticket_T'].astype(str) + "_" + match3['Poids_Terrain'].astype(str)
                 final_t['UID_T'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str)
                 uids3 = match3['UID_T'].unique(); final_t = final_t[~final_t['UID_T'].isin(uids3)]; final_f = final_f[~final_f['Num Ticket'].isin(matched_tf)]
                 
    cols_t = df_ter.columns; cols_f = df_ref.columns
    orph_t = final_t.rename(columns={c: c + '_T' for c in cols_t}); orph_f = final_f.rename(columns={c: c + '_F' for c in cols_f})
    orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'; orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    final = pd.concat([match1, match2, match3, orph_t, orph_f], ignore_index=True); final['Exutoire'] = "PICHETA INOE"
    
    if 'Num Ticket_F' in final.columns: final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else: final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
    final['Num Bon'] = resolve_col(final, 'Num Bon').fillna('').astype(str); final['Date_Ref'] = resolve_col(final, 'Date_Ref').apply(convertir_date_robuste)
    final['Immatriculation'] = resolve_col(final, 'Immatriculation').fillna('').astype(str)
    p_tt = pd.to_numeric(final.get('Poids_Terrain_T', 0), errors='coerce').fillna(0); final['Poids_Terrain'] = pd.to_numeric(final.get('Poids_Terrain', 0), errors='coerce').fillna(0)
    final['Poids_Terrain'] = np.where(final['Poids_Terrain'] > 0, final['Poids_Terrain'], p_tt)
    p_ff = pd.to_numeric(final.get('Poids_Facture_F', 0), errors='coerce').fillna(0); final['Poids_Facture'] = pd.to_numeric(final.get('Poids_Facture', 0), errors='coerce').fillna(0)
    final['Poids_Facture'] = np.where(final['Poids_Facture'] > 0, final['Poids_Facture'], p_ff)
    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']; final['INT Client'] = final.get('Client_T', final.get('Client')).fillna("GPSEO").astype(str); final['EXT Client'] = final.get('Client_F').fillna("").astype(str)
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext'); final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"; final['Activité'] = resolve_col(final, 'Activité').fillna("DECH")
    
    def check_client_picheta(row):
        int_c = str(row.get('INT Client', '')).upper().strip(); ext_c = str(row.get('EXT Client', '')).upper().strip()
        if not int_c or not ext_c: return "OK"
        if int_c == ext_c: return "OK"
        k1 = normalize_site_key(int_c); k2 = normalize_site_key(ext_c)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        return "OK" if s1.intersection(s2) else "Pb.Clt"

    final['Verif_Client'] = final.apply(check_client_picheta, axis=1)
    return final
