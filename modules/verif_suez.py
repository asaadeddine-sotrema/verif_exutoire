import pandas as pd
import numpy as np
import logging
import streamlit as st
import re

logger = logging.getLogger(__name__)

DICT_CORRECTION_SUEZ = {
    "CTC MUREAUX": "CTC LES MUREAUX",
    "DECHETTERIE MLJ CLOSEAUX 1": "DECHETERIE DES CLOSEAUX MANTES LA J",
    "DECHETTERIE MLJ CLOSEAUX 2": "DECHETERIE DES CLOSEAUX MANTES LA J",
    "DECHETTERIE MLV VAUCOULEURS": "DECHETTERIE DE LA VAUCOULEURS"
}

def convertir_date_suez(val):
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (pd.Timestamp, pd.datetime, pd.Timestamp)):
        return val.date()
    v_str = str(val).strip()
    if re.match(r"^\d{2}/\d{2}/\d{4}", v_str):
        try: return pd.to_datetime(v_str, format='%d/%m/%Y').date()
        except: pass
    try:
        dt = pd.to_datetime(v_str, errors='coerce')
        if pd.notna(dt): return dt.date()
    except: pass
    return pd.NaT

def normalize_site_key(txt):
    if pd.isna(txt) or not str(txt).strip(): return "NAN"
    t = str(txt).upper().strip()
    # On enlève les accents et caractères spéciaux
    import unicodedata
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    # On garde que les Alphanumériques et espaces
    t = re.sub(r'[^A-Z0-9 ]', ' ', t)
    # On enlève les mots trop courts ou bruits
    mots = [m for m in t.split() if len(m) > 2]
    return " ".join(mots) if mots else "EMPTY"

def check_site_keys(row):
    k1 = str(row.get('Key_Site_T', ''))
    k2 = str(row.get('Key_Site_F', ''))
    if k1 == "NAN" or k2 == "NAN": return True # On laisse passer si manque
    s1 = set(k1.split())
    s2 = set(k2.split())
    if s1.intersection(s2): return True
    return False

def restore_columns(df, suffix, original_cols):
    res = df.copy()
    for col in original_cols:
        target = col + suffix
        if target in res.columns:
            res[col] = res[target]
    return res[original_cols]

def charger_suez_terrain(f, type_fichier):
    try:
        df = pd.read_excel(f, header=0, dtype=str)
        # Mapping colonnes CTC vs DECH
        cols_map = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "n° ticket" in cl: cols_map[c] = "Num Ticket"
            if "n° bon" in cl or "numéro de bon" in cl: cols_map[c] = "Num Bon"
            if "date ticket" in cl or "date du bon" in cl: cols_map[c] = "Date_Ref"
            if "poids net" in cl or "poids (t)" in cl: cols_map[c] = "Poids_Terrain"
            if "immat" in cl: cols_map[c] = "Immatriculation"
            if "chauffeur" in cl: cols_map[c] = "Chauffeur"
            if "client" in cl or "provenance" in cl: cols_map[c] = "Client"
            if "matière" in cl or "libellé matière" in cl: cols_map[c] = "Matiere_T"

        df = df.rename(columns=cols_map)
        
        if 'Poids_Terrain' in df.columns:
            df['Poids_Terrain'] = pd.to_numeric(df['Poids_Terrain'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            if df['Poids_Terrain'].max() > 100: df['Poids_Terrain'] = df['Poids_Terrain'] / 1000
            
        if 'Client' in df.columns:
             df['Client'] = df['Client'].astype(str).str.upper().str.strip()
             for k, v in DICT_CORRECTION_SUEZ.items():
                 df['Client'] = df['Client'].replace(k, v)
             df['Client'] = df['Client'].astype(str).replace(['nan', 'None', '', 'NAN'], np.nan)
        
        df['Activité'] = type_fichier
        
        if 'Date_Ref' in df.columns:
            df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_suez)

        logger.info(f"Charge Suez {type_fichier}: {len(df)} lignes")
        return df
    except Exception as e: 
        logger.error(f"Erreur chargement {type_fichier}: {e}", exc_info=True)
        st.error(f"Erreur chargement {type_fichier}: {e}")
        return pd.DataFrame()

def process_suez(f_ctc, f_dech, f_fac):
    logger.info("Début traitement SUEZ")
    dfs = []
    if f_ctc: dfs.append(charger_suez_terrain(f_ctc, "CTC"))
    if f_dech: dfs.append(charger_suez_terrain(f_dech, "DECH"))
    
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    if 'Poids_Terrain' not in df_ter.columns: df_ter['Poids_Terrain'] = 0
    
    df_ref = pd.read_excel(f_fac, header=0, dtype=str)

    col_target = None
    col_transp = None
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "nom recherche client" in cl: col_target = c
        if "nom recherche transporteur" in cl: col_transp = c
        
    if col_target:
        df_ref = df_ref[df_ref[col_target].astype(str).str.upper().str.strip() == 'GPSEOAUB']
        
    if col_transp:
        df_ref = df_ref[df_ref[col_transp].astype(str).str.upper().str.strip() == 'K0ESOTRE']
    
    cols_ref = {}
    col_ext_client_found = False

    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° bon de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "quantité nette" in cl: cols_ref[c] = "Poids_Facture"
        if "humidité" in cl: cols_ref[c] = "Poids_Humidite"
        if "date du bon" in cl: cols_ref[c] = "Date_Ref"
        if "nom recherche client" in cl: cols_ref[c] = "Billing_Client"
        
        if "nom de l'adresse de service" in cl:
             cols_ref[c] = "EXT Client"
             col_ext_client_found = True
             
        elif "ville de l'adresse de service" in cl:
             if not col_ext_client_found:
                 cols_ref[c] = "EXT Client"
                 col_ext_client_found = True
             
        elif ("chantier" in cl or "producteur" in cl ) and "nom" in cl:
             if not col_ext_client_found:
                 cols_ref[c] = "EXT Client"
                 col_ext_client_found = True
        
        if "description déchet" in cl: cols_ref[c] = "EXT_Matiere"
        if "immatriculation" in cl: cols_ref[c] = "Immatriculation"

    if not col_ext_client_found:
        for c in df_ref.columns:
            if "nom de l'adresse de service" in str(c).lower():
                cols_ref[c] = "EXT Client"

    df_ref = df_ref.rename(columns=cols_ref)
    df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]
    
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    if 'Date_Ref' in df_ref.columns:
        df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_suez)
    
    if 'Poids_Facture' in df_ref.columns:
        p_net = pd.to_numeric(df_ref['Poids_Facture'], errors='coerce').fillna(0)
        p_hum = pd.to_numeric(df_ref['Poids_Humidite'], errors='coerce').fillna(0) if 'Poids_Humidite' in df_ref.columns else 0
        df_ref['Poids_Facture'] = (p_net + p_hum) / 1000

    cols_ter = df_ter.columns.tolist()
    cols_ref_list = df_ref.columns.tolist()

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

    left1 = m1[m1['_merge'] == 'left_only'].copy()
    right1 = m1[m1['_merge'] == 'right_only'].copy()

    l_ter = restore_columns(left1, '_T', cols_ter)
    l_ref = restore_columns(right1, '_F', cols_ref_list)

    match2 = pd.DataFrame()
    
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")

        l_ter_valid = l_ter[l_ter['Key_Date'] != "NAN"].copy()
        l_ref_valid = l_ref[l_ref['Key_Date'] != "NAN"].copy()

        l_ter['Key_Site'] = l_ter['Client'].apply(normalize_site_key)
        l_ref['Key_Site'] = l_ref['EXT Client'].apply(normalize_site_key)
        
        if not l_ter_valid.empty and not l_ref_valid.empty:
             m_cross = pd.merge(l_ter_valid, l_ref_valid, on='Key_Date', how='inner', suffixes=('_T', '_F'))
        else:
             m_cross = pd.DataFrame()
        
        if not m_cross.empty:
            p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
            p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
            m_cross['Delta_Poids'] = (p_t - p_f).abs()
            
            candidates = m_cross[m_cross['Delta_Poids'] <= 0.5].copy()

            if not candidates.empty:
                candidates['Client_OK'] = candidates.apply(check_site_keys, axis=1)
                candidates = candidates[(candidates['Client_OK'] == True) | (candidates['Delta_Poids'] <= 0.005)]
            
            candidates = candidates.sort_values('Delta_Poids')
            
            if 'Num Bon' in candidates.columns:
                match2 = candidates.drop_duplicates(subset=['Num Bon'], keep='first')
            else:
                match2 = candidates.drop_duplicates(subset=['Key_Date', 'Poids_Terrain'], keep='first')

            if 'Num Ticket_F' in match2.columns:
                match2 = match2.drop_duplicates(subset=['Num Ticket_F'], keep='first')

            if not match2.empty:
                match2['Methode'] = '2. Rapprochement Tolérant'
                match2['_merge'] = 'both'

                if 'Num Ticket_F' in match2.columns:
                    match2['Num Ticket'] = match2['Num Ticket_F']

                matched_bons = match2['Num Bon'].tolist() if 'Num Bon' in match2.columns else []
                matched_tickets_fac = match2['Num Ticket_F'].tolist() if 'Num Ticket_F' in match2.columns else []

                final_t = l_ter[~l_ter['Num Bon'].isin(matched_bons)]
                
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

    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
         offset_dfs = []
         final_t['Date_Obj'] = pd.to_datetime(final_t['Date_Ref'], errors='coerce')
         final_f['Date_Obj'] = pd.to_datetime(final_f['Date_Ref'], errors='coerce')
         
         f_t_clean = final_t.dropna(subset=['Date_Obj']).copy()
         f_f_clean = final_f.dropna(subset=['Date_Obj']).copy()
         
         if not f_t_clean.empty and not f_f_clean.empty:
             for offset in range(-2, 3):
                 temp = f_t_clean.copy()
                 temp['Join_Date'] = temp['Date_Obj'] + pd.Timedelta(days=offset)
                 temp['_Offset'] = offset
                 offset_dfs.append(temp)
             
             t_expanded = pd.concat(offset_dfs)
             m_flex = pd.merge(t_expanded, f_f_clean, left_on='Join_Date', right_on='Date_Obj', how='inner', suffixes=('_T', '_F'))
             
             if not m_flex.empty:
                 p_t = pd.to_numeric(m_flex['Poids_Terrain'], errors='coerce').fillna(0)
                 p_f = pd.to_numeric(m_flex['Poids_Facture'], errors='coerce').fillna(0)
                 m_flex['Delta_Poids'] = (p_t - p_f).abs()
                 m_flex['Delta_Days'] = m_flex['_Offset'].abs()
                 candidates_3 = m_flex[m_flex['Delta_Poids'] <= 0.5].copy()
                 
                 if not candidates_3.empty:
                     candidates_3 = candidates_3.sort_values(['Delta_Days', 'Delta_Poids'])
                     if 'Num Bon' in candidates_3.columns:
                         match3 = candidates_3.drop_duplicates(subset=['Num Bon'], keep='first')
                     else:
                         match3 = candidates_3.drop_duplicates(subset=['Date_Ref_T', 'Poids_Terrain'], keep='first')
                     
                     if not match3.empty:
                         match3['Methode'] = '3. Rapprochement Date Flexible'
                         match3['_merge'] = 'both'
                         match3['Date_Ref'] = match3['Date_Ref_T']
                         if 'Num Ticket_F' in match3.columns:
                            match3['Num Ticket'] = match3['Num Ticket_F']

                         def make_uid(df, s):
                              return df[f'Num Ticket{s}'].astype(str) + "_" + df[f'Poids_Terrain{"" if s=="_T" else ""}'].astype(str) + "_" + df[f'Date_Ref{s}'].astype(str)

                         matched_uids_t = make_uid(match3, '_T').tolist()
                         matched_uids_f = make_uid(match3, '_F').tolist()
                         
                         final_t['_UID_CLEAN'] = final_t['Num Ticket'].astype(str) + "_" + final_t['Poids_Terrain'].astype(str) + "_" + final_t['Date_Ref'].astype(str)
                         final_f['_UID_CLEAN'] = final_f['Num Ticket'].astype(str) + "_" + final_f['Poids_Facture'].astype(str) + "_" + final_f['Date_Ref'].astype(str)
                         
                         final_t = final_t[~final_t['_UID_CLEAN'].isin(matched_uids_t)].drop(columns=['_UID_CLEAN'])
                         final_f = final_f[~final_f['_UID_CLEAN'].isin(matched_uids_f)].drop(columns=['_UID_CLEAN'])
                         
                         for c in ['Date_Obj_T', 'Date_Obj_F', 'Join_Date', '_Offset', 'Delta_Days', 'Delta_Poids']:
                             if c in match3.columns: match3 = match3.drop(columns=[c])

         if 'Date_Obj' in final_t.columns: final_t = final_t.drop(columns=['Date_Obj'])
         if 'Date_Obj' in final_f.columns: final_f = final_f.drop(columns=['Date_Obj'])

    orph_t = final_t.rename(columns={c: c + '_T' for c in cols_ter})
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_ref_list})
    
    orph_t['_merge'] = 'left_only'
    orph_t['Methode'] = 'Non Trouvé'
    orph_f['Methode'] = 'Non Trouvé'

    merged = pd.concat([match1, match2, match3, orph_t, orph_f], ignore_index=True)
    merged['Exutoire'] = "SUEZ"
    
    def resolve_col(df, col_base):
        fallback = pd.Series([np.nan] * len(df), index=df.index)
        c_t = df.get(f"{col_base}_T", fallback)
        c_f = df.get(f"{col_base}_F", fallback)
        if col_base in df.columns:
            return df[col_base].fillna(c_t).fillna(c_f)
        return c_t.fillna(c_f)

    merged['Num Ticket'] = resolve_col(merged, 'Num Ticket').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    c_nb = merged.get('Num Bon', pd.Series([np.nan]*len(merged)))
    c_nb_t = merged.get('Num Bon_T', pd.Series([np.nan]*len(merged)))
    c_nb_f = merged.get('Num Bon_F', pd.Series([np.nan]*len(merged)))
    merged['Num Bon'] = c_nb.fillna(c_nb_t).fillna(c_nb_f).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['Date'] = resolve_col(merged, 'Date_Ref')
    
    for c_base in ['Immatriculation', 'Chauffeur']:
        merged[c_base] = resolve_col(merged, c_base).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')

    merged['Activité'] = resolve_col(merged, 'Activité').fillna('SUEZ')
    merged['Matiere_T'] = resolve_col(merged, 'Matiere_T')
    merged['EXT_Matiere'] = resolve_col(merged, 'EXT_Matiere')
    merged['Dechetterie'] = resolve_col(merged, 'Client')

    p_ter = pd.to_numeric(merged.get('Poids_Terrain', np.nan), errors='coerce').fillna(0)
    p_ter_t = pd.to_numeric(merged.get('Poids_Terrain_T', np.nan), errors='coerce').fillna(0)
    merged['Poids_Terrain'] = np.where(p_ter > 0, p_ter, p_ter_t)
    
    p_fac = pd.to_numeric(merged.get('Poids_Facture', np.nan), errors='coerce').fillna(0)
    p_fac_f = pd.to_numeric(merged.get('Poids_Facture_F', np.nan), errors='coerce').fillna(0)
    if p_fac.max() > 100: p_fac = p_fac / 1000
    if p_fac_f.max() > 100: p_fac_f = p_fac_f / 1000
    merged['Poids_Facture'] = np.where(p_fac > 0, p_fac, p_fac_f)
    
    merged['Poids_Terrain'] = np.where(merged['Poids_Terrain'] >= 99, 0, merged['Poids_Terrain'])
    merged['Poids_Facture'] = np.where(merged['Poids_Facture'] >= 99, 0, merged['Poids_Facture'])
    merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
    merged['INT Client'] = merged['Dechetterie'].fillna("GPSEO").astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['Client'] = "GPSEO"
    
    ext_c = merged.get('EXT Client', pd.Series([np.nan]*len(merged)))
    ext_cf = merged.get('EXT Client_F', pd.Series([np.nan]*len(merged)))
    merged['EXT Client'] = ext_c.combine_first(ext_cf).fillna('GPSEOAUB').astype(str).replace(['nan', 'NAN', 'None'], '')

    def patch_ticket_st(row):
        t = str(row.get('Num Ticket', '')).strip().upper()
        b = str(row.get('Num Bon', '')).strip().upper()
        mauvais_tickets = ['ST', 'NAN', '', 'NONE', '0', 'None']
        if t in mauvais_tickets and b not in mauvais_tickets: return f"A_CORRIGER_{b}"
        return t

    merged['Num Ticket'] = merged.apply(patch_ticket_st, axis=1)
    merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})
    merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.01).replace({True:'OK', False:'Pb.T'})
    
    def check_client_suez(row):
        int_c = str(row.get('INT Client', '')).upper().strip()
        ext_c = str(row.get('EXT Client', '')).upper().strip()
        if not int_c or not ext_c: return "OK"
        if int_c == ext_c: return "OK"
        k1 = normalize_site_key(int_c)
        k2 = normalize_site_key(ext_c)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
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
    
    # Import from main app if possible or define if not available
    try:
        from app import verify_aggregated_weights
        merged = verify_aggregated_weights(merged)
    except:
        pass
        
    return merged[cols_final]
