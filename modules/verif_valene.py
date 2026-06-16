import pandas as pd
import numpy as np
import logging
import streamlit as st
import re
import unicodedata
from datetime import datetime, date

# --- LOGGER ---
logger = logging.getLogger(__name__)

# --- UTILS (Copied or imported if possible) ---
def convertir_date_robuste(val):
    """Imported from main app logic if possible, otherwise fallback"""
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (date, datetime, pd.Timestamp)): 
        return val.date() if isinstance(val, (pd.Timestamp, datetime)) else val
    v_str = str(val).strip()
    
    # 1. Tentative Excel Serial
    try:
        val_num = float(v_str)
        if val_num > 30000:
            return pd.to_datetime(val_num, unit='D', origin='1899-12-30').date()
    except:
        pass

    # 2. FORMATS ISO
    if len(v_str) >= 10 and v_str[4] == '-' and v_str[7] == '-' and v_str[0:4].isdigit():
        try:
            return datetime.strptime(v_str[:10], "%Y-%m-%d").date()
        except:
            pass

    # 3. FORMATS FRANÇAIS STRICTS
    for fmt in ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"]:
        try:
            return datetime.strptime(v_str, fmt).date()
        except:
            continue
            
    # 4. Fallback Pandas avec dayfirst=True
    try:
        dt = pd.to_datetime(v_str, dayfirst=True, errors='coerce')
        if pd.notna(dt): return dt.date()
    except:
        pass
        
    return pd.NaT

def normalize_site_key(txt):
    if not txt or pd.isna(txt): return "NAN"
    t = str(txt).lower()
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'[^a-z0-9]', ' ', t)
    return " ".join(t.split())

def normaliser_matiere_valene(m):
    if not m or pd.isna(m): return ""
    s = str(m).upper().strip()
    # Remplacer É par E pour les ordures ménagères (et similaires)
    s = s.replace("É", "E").replace("È", "E")
    
    if "PAPIER" in s or "CARTON" in s: return "PAPIERS/CARTONS"
    if "EMBALLAGE" in s or "PAV" in s: return "EMBALLAGES MENAGERS RECYCLABLES"
    if "DECHETS INDUSTRIELS BANALS" in s or "DIB" in s or "INCINERABLE" in s: return "ORDURES MENAGERES"
    if "SOTREMA" in s: return "MENAGERS"
    return s

def normaliser_matiere_picheta_valoseine(m):
    if not m or pd.isna(m): return ""
    import unicodedata
    s = str(m).upper().strip()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    v = s.lower()
    
    # RAPPEL MAP PICHETA GLOBALE
    if 'vegetau' in v or 'dve' in v or 'verts' in v:
        return 'DEPOT VEGETAUX TVA10 - BPU 4.2'
    if 'carton' in v:
        return 'DEPOT PAPIER CARTON TVA0 - BPU 4.7'
    if 'gravat' in v:
        return 'DEPOT GRAVAT CHANTIER TVA10 - BPU 4.1'
    if 'platre' in v:
        return 'DEPOT PLATRE TVA5.5 - BPU 4.8'
    if 'ferraille' in v:
        return 'DEPOT FERRAILLE TVA0 - BPU 4.6'
    
    # SPECIFIC MAPPINGS FOR VALOSEINE IF ANY (fallback)
    if "BOIS" in s: return "BOIS"
    if "ENCOMBRANTS" in s: return "DIB"
    if "TOUT VENANT" in s: return "TOUT VENANT"
    
    return str(m)

def resolve_col(df, base_name):
    """Helper to find a column even if it was renamed with _T or _F suffixes"""
    ct, cf = f"{base_name}_T", f"{base_name}_F"
    fallback = pd.Series([np.nan]*len(df), index=df.index)
    c_t = df.get(ct, fallback)
    c_f = df.get(cf, fallback)
    
    if base_name in df.columns:
        return df[base_name].fillna(c_t).fillna(c_f)
    return c_t.fillna(c_f)

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
        if hasattr(f, 'seek'): f.seek(0)
        df = pd.read_excel(f, header=idx, dtype=str)
        cols = {}
        for c in df.columns:
            cl = str(c).lower()
            if "ticket" in cl: cols[c] = "Num Ticket"
            if "poids" in cl and "tonnes" in cl: cols[c] = "Poids_Terrain"
            if "poids net" in cl: cols[c] = "Poids_KG"
            if "matière" in cl or "description" in cl: cols[c] = "Matiere_T"
            if cl in ["date", "le", "journee"]: cols[c] = "Date_Ref"
            elif "date" in cl: cols[c] = "Date_Ref"
            if "client" in cl: cols[c] = "Client"
            if "bon" in cl: cols[c] = "Num Bon"
            if "chauffeur" in cl or "conducteur" in cl: cols[c] = "Chauffeur"
            if "immat" in cl or "véhicule" in cl: cols[c] = "Immatriculation"
        df = df.rename(columns=cols)
        df = df.loc[:, ~df.columns.duplicated()]
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

def process_valene(f_sot, f_exp):
    logger.info("Début traitement VALENE")
    dfs = []
    # if f_pap: dfs.append(charger_valene(f_pap, "PAP"))
    # if f_pav: dfs.append(charger_valene(f_pav, "PAV"))
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
        if "immatriculation" in cl or "véhicule" in cl: cols_ref[c] = "Immatriculation"
        if "date" in cl: cols_ref[c] = "Date_Ref"
    df_ref = df_ref.rename(columns=cols_ref); df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]
    if 'Date_Ref' in df_ref.columns:
        df_ref['Date_Ref'] = df_ref['Date_Ref'].apply(convertir_date_robuste)

    # Filtre les lignes de la facture pour ne conserver que celles dont le client contient SOTREMA
    client_cols = [c for c in df_ref.columns if 'client' in str(c).lower()]
    if client_cols:
        mask_sot = pd.Series(False, index=df_ref.index)
        for c in client_cols:
            mask_sot |= df_ref[c].astype(str).str.contains('SOTREMA', case=False, na=False)
        df_ref = df_ref[mask_sot].copy()
    
    # Nettoyage des lignes completement vides
    df_ter = df_ter.dropna(how='all', subset=[c for c in df_ter.columns if c not in ['Activité', 'Client']])
    df_ref = df_ref.dropna(how='all')
    
    # Nettoyage des lignes vides ou sous-totaux (sans Date ET sans Ticket)
    if 'Date_Ref' in df_ref.columns and 'Num Ticket' in df_ref.columns:
        mask_empty = (
            (df_ref['Num Ticket'].isna() | (df_ref['Num Ticket'].astype(str).str.strip() == '') | (df_ref['Num Ticket'].astype(str).str.lower().isin(['nan', 'nat', 'none']))) &
            (df_ref['Date_Ref'].isna() | (df_ref['Date_Ref'].astype(str).str.strip() == '') | (df_ref['Date_Ref'].astype(str).str.lower().isin(['nan', 'nat', 'none'])))
        )
        df_ref = df_ref[~mask_empty].copy()
    
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)
    df_ter['Matiere_T'] = df_ter['Matiere_T'].apply(normaliser_matiere_valene)
    
    # Nettoyage des sous-totaux dans la facture Valene
    mask_subtotal = df_ref.apply(lambda r: any(str(v).strip().lower() in ['total', 'sous-total', 'sous total'] or str(v).strip().lower().startswith('total ') for v in r), axis=1)
    df_ref = df_ref[~mask_subtotal].copy()
    
    if 'EXT_Matiere' in df_ref.columns: df_ref['EXT_Matiere_Norm'] = df_ref['EXT_Matiere'].apply(normaliser_matiere_valene)
    else: df_ref['EXT_Matiere_Norm'] = ""
    # --------- SMART MATCH VALENE ---------
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace('NAN', np.nan).replace('', np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace('NAN', np.nan).replace('', np.nan)

    # 1. Match Exact sur Ticket
    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'

    matched_ids_t = match1['K'].unique()
    matched_ids_f = match1['K'].unique()
    l_ter = df_ter[~df_ter['K'].isin(matched_ids_t)].copy()
    l_ref = df_ref[~df_ref['K'].isin(matched_ids_f)].copy()

    # 2. Match Intelligent sur Date et Poids (pour la facturation sans ticket ou erreur)
    match2 = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN") if 'Date_Ref' in l_ter.columns else "NAN"
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN") if 'Date_Ref' in l_ref.columns else "NAN"
        
        l_ter_valid = l_ter[l_ter['Key_Date'] != "NAN"].copy()
        l_ref_valid = l_ref[l_ref['Key_Date'] != "NAN"].copy()

        # PRE-AGREGATION des tickets Terrain sur le Num Bon
        # Parfois, il y a 2 tickets pour 1 seul bon, et Valene ne fournit pas Num Bon dans sa facture
        if 'Num Bon' in l_ter_valid.columns:
            # Séparer les lignes avec bons valides des lignes sans bon
            mask_has_bon_ter = l_ter_valid['Num Bon'].astype(str).str.strip().str.upper().replace(['NAN', 'NONE', '0', '0.0', ''], np.nan).notna()
            ter_with_bon = l_ter_valid[mask_has_bon_ter].copy()
            ter_no_bon = l_ter_valid[~mask_has_bon_ter].copy()
            
            # Agréger les poids pour les mêmes Bons le même jour
            if not ter_with_bon.empty:
                ter_with_bon['Poids_Terrain'] = pd.to_numeric(ter_with_bon['Poids_Terrain'], errors='coerce').fillna(0)
                
                agg_funcs = {c: 'first' for c in ter_with_bon.columns if c != 'Poids_Terrain' and c != 'Num Ticket'}
                agg_funcs['Poids_Terrain'] = 'sum'
                agg_funcs['Num Ticket'] = lambda x: ' + '.join(x.astype(str))
                
                ter_agg = ter_with_bon.groupby(['Key_Date', 'Num Bon'], as_index=False).agg(agg_funcs)
                l_ter_valid = pd.concat([ter_agg, ter_no_bon], ignore_index=True)

        if not l_ter_valid.empty and not l_ref_valid.empty:
            m_cross = pd.merge(l_ter_valid, l_ref_valid, on='Key_Date', how='inner', suffixes=('_T', '_F'))
            if not m_cross.empty:
                p_t = pd.to_numeric(m_cross['Poids_Terrain'], errors='coerce').fillna(0)
                p_f = pd.to_numeric(m_cross['Poids_Facture'], errors='coerce').fillna(0)
                m_cross['Delta_Poids'] = (p_t - p_f).abs()
                
                # Tolérance de 0.5 T pour le rapprochement
                candidates = m_cross[m_cross['Delta_Poids'] <= 0.5].copy()
                candidates = candidates.sort_values('Delta_Poids')
                
                match2 = candidates.drop_duplicates(subset=['Key_Date', 'Poids_Terrain'], keep='first')
                
                if not match2.empty:
                    match2['Methode'] = '2. Rapprochement Intelligent'
                    match2['_merge'] = 'both'
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
    else: 
        final_t, final_f = l_ter, l_ref

    # 3. Match 3 : Agrégation Journalière Combinatoire (Sans Plaque d'Immat)
    match3 = pd.DataFrame()
    if not final_t.empty and not final_f.empty:
        valid_t = final_t[final_t['Key_Date'] != "NAN"].copy()
        valid_f = final_f[final_f['Key_Date'] != "NAN"].copy()

        if not valid_t.empty and not valid_f.empty:
            valid_t['Poids_Terrain'] = pd.to_numeric(valid_t['Poids_Terrain'], errors='coerce').fillna(0)
            valid_f['Poids_Facture'] = pd.to_numeric(valid_f['Poids_Facture'], errors='coerce').fillna(0)
            
            # Essayer de trouver pour chaque date s'il y a un groupe de lignes dont la somme correspond (erreur < 0.5T)
            # Puisque l'immatriculation n'est pas fiable, on va grouper par Date globale.
            # ATTENTION: Si on groupe tout sur une date, on risque de fusionner des camions différents,
            # on va donc chercher des combinaisons.
            
            # Approche simplifiée: Pour chaque Date, si la Somme(Terrain) ~= Somme(Facture), on agrège TOUT.
            agg_t = {c: 'first' for c in valid_t.columns if c not in ['Poids_Terrain', 'Num Ticket', 'Num Bon', 'Key_Date']}
            agg_t['Poids_Terrain'] = 'sum'
            agg_t['Num Ticket'] = lambda x: ' + '.join(x.dropna().astype(str))
            agg_t['Num Bon'] = lambda x: ' + '.join(x.dropna().astype(str).unique())
            group_t = valid_t.groupby(['Key_Date'], as_index=False).agg(agg_t)
            
            agg_f = {c: 'first' for c in valid_f.columns if c not in ['Poids_Facture', 'Num Ticket', 'Key_Date']}
            agg_f['Poids_Facture'] = 'sum'
            agg_f['Num Ticket'] = lambda x: ' + '.join(x.dropna().astype(str))
            group_f = valid_f.groupby(['Key_Date'], as_index=False).agg(agg_f)

            m_cross3 = pd.merge(group_t, group_f, on=['Key_Date'], how='inner', suffixes=('_T', '_F'))
            if not m_cross3.empty:
                m_cross3['Delta_Poids'] = (m_cross3['Poids_Terrain'] - m_cross3['Poids_Facture']).abs()
                candidates3 = m_cross3[m_cross3['Delta_Poids'] <= 0.5].copy()
                
                if not candidates3.empty:
                    match3 = candidates3.copy()
                    match3['Methode'] = '3. Cumul Journalier Total'
                    match3['_merge'] = 'both'
                    
                    # Retirer les lignes utilisées
                    used_keys = match3['Key_Date'].tolist()
                    final_t = final_t[~final_t['Key_Date'].isin(used_keys)]
                    final_f = final_f[~final_f['Key_Date'].isin(used_keys)]
                    
                    match3 = match3.drop(columns=['Delta_Poids'])

    # Orphelins
    cols_ter_orig = df_ter.columns
    cols_ref_orig = df_ref.columns
    final_orph_t = final_t.rename(columns={c: str(c) + '_T' for c in cols_ter_orig})
    final_orph_f = final_f.rename(columns={c: str(c) + '_F' for c in cols_ref_orig})
    final_orph_t['_merge'] = 'left_only'
    final_orph_t['Methode'] = 'Non Trouvé'
    final_orph_f['_merge'] = 'right_only'
    final_orph_f['Methode'] = 'Non Trouvé'

    merged = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True)
    # ----------------------------------------
    
    # ----------------------------------------
    
    # 4. Resolution of key columns before verification
    # This ensures that even orphans (Pb.EXT) have their data (INT Client, EXT Client, Matiere) populated
    
    # Resolution of Client
    final_int_c = resolve_col(merged, 'INT Client')
    final_ext_c = resolve_col(merged, 'EXT Client')
    # Fallbacks from original Client columns
    c_cl_t = merged.get('Client_T', pd.Series([np.nan]*len(merged)))
    c_cl_f = merged.get('Client_F', pd.Series([np.nan]*len(merged)))
    
    merged['INT Client'] = final_int_c.fillna(c_cl_t).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['EXT Client'] = final_ext_c.fillna(c_cl_f).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    
    # Resolution of Matiere
    final_mat_t = resolve_col(merged, 'Matiere_T')
    final_mat_f = resolve_col(merged, 'EXT_Matiere')
    # Use resolve_col for EXT_Matiere_Norm as well
    final_mat_f_norm = resolve_col(merged, 'EXT_Matiere_Norm')
    
    merged['Matiere_T'] = final_mat_t.fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['EXT_Matiere'] = final_mat_f.fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['EXT_Matiere_Norm'] = final_mat_f_norm.fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')

    # Resolution of Num Ticket and Date
    if 'Num Ticket_F' in merged.columns:
        merged['Num Ticket'] = merged['Num Ticket_F'].fillna(merged.get('Num Ticket_T')).fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    else:
        merged['Num Ticket'] = resolve_col(merged, 'Num Ticket').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')

    c_dt_t = merged.get('Date_Ref_T', pd.Series([np.nan]*len(merged)))
    c_dt_f = merged.get('Date_Ref_F', pd.Series([np.nan]*len(merged)))
    merged['Date_Ref'] = resolve_col(merged, 'Date_Ref').fillna(c_dt_t).fillna(c_dt_f)

    # Resolution of other metadata
    c_ch_t = merged.get('Chauffeur_T', pd.Series([np.nan]*len(merged)))
    c_ch_f = merged.get('Chauffeur_F', pd.Series([np.nan]*len(merged)))
    merged['Chauffeur'] = resolve_col(merged, 'Chauffeur').fillna(c_ch_t).fillna(c_ch_f)

    c_im_t = merged.get('Immatriculation_T', pd.Series([np.nan]*len(merged)))
    c_im_f = merged.get('Immatriculation_F', pd.Series([np.nan]*len(merged)))
    merged['Immatriculation'] = resolve_col(merged, 'Immatriculation').fillna(c_im_t).fillna(c_im_f)
    
    merged['Num Bon'] = resolve_col(merged, 'Num Bon').fillna('').astype(str).replace(['nan', 'NAN', 'None'], '')
    merged['Exutoire'] = "VALENE"
    
    # Resolution of Weights
    p_ter_t = pd.to_numeric(merged.get('Poids_Terrain_T', 0), errors='coerce').fillna(0)
    merged['Poids_Terrain'] = pd.to_numeric(resolve_col(merged, 'Poids_Terrain'), errors='coerce').fillna(0)
    merged['Poids_Terrain'] = np.where(merged['Poids_Terrain'] > 0, merged['Poids_Terrain'], p_ter_t)

    p_fac_f = pd.to_numeric(merged.get('Poids_Facture_F', 0), errors='coerce').fillna(0)
    merged['Poids_Facture'] = pd.to_numeric(resolve_col(merged, 'Poids_Facture'), errors='coerce').fillna(0)
    merged['Poids_Facture'] = np.where(merged['Poids_Facture'] > 0, merged['Poids_Facture'], p_fac_f)

    merged['Poids_Terrain'] = np.floor(merged['Poids_Terrain'] * 100) / 100
    merged['Poids_Facture'] = np.floor(merged['Poids_Facture'] * 100) / 100
    
    merged['Poids_Terrain'] = np.where(merged['Poids_Terrain'] >= 99, 0, merged['Poids_Terrain'])
    merged['Poids_Facture'] = np.where(merged['Poids_Facture'] >= 99, 0, merged['Poids_Facture'])
    
    merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
    
    merged['Verif_Exutoire'] = np.where(merged['_merge'] == 'both', 'OK', 'Pb.Ext')
    merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'})
    merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
    
    # Handle GPSEO variations
    merged['INT Client'] = merged['INT Client'].astype(str).replace(['CU GPSO', 'GPSO'], 'GPSEO').replace(['nan', 'NAN', 'None'], '')
    merged['Client'] = merged['INT Client'].copy() # Re-sync Client with INT Client

    def verif_client(row):
        c_int = str(row.get('INT Client', '')).upper().strip()
        c_ext = str(row.get('EXT Client', '')).upper().strip()
        act = str(row.get('Activité', '')).upper()
        if not c_int or not c_ext: return "OK"
        if "SOTREMA2" in act:
            if "GPSEO" not in c_int: return "OK"
        
        # Extended match for GPSEO
        if c_int in ["GPSEO", "CCPIF"]:
            if any(k in c_ext for k in ["GRAND PARIS SEINE ET OISE", "CU GPSO", "GPSO"]):
                return "OK"
                
        if c_int in c_ext or c_ext in c_int: return "OK"
        return "Pb.Clt"

    merged['Verif_Client'] = merged.apply(verif_client, axis=1)
    
    if 'Date' in merged.columns: merged = merged.drop(columns=['Date'])
    merged = merged.rename(columns={'Date_Ref': 'Date'})
    
    cols_final = ['Date', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
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
        keywords = ['ticket', 'tp manuel', 'bon', 'tonnages', 'date', 'immatriculation', 'chauffeur', 'le', 'journee']
        
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
            elif cl in ["date", "le", "journee"]: cols[c] = "Date_Ref"
            elif "date" in cl: cols[c] = "Date_Ref"
            elif "nchantier" in cl: cols[c] = "Client"
            elif "immatriculation" in cl: cols[c] = "Immatriculation"
            elif "chauffeur" in cl: cols[c] = "Chauffeur"
            
        df = df.rename(columns=cols)
        df = df.loc[:, ~df.columns.duplicated()]
        
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
            
    if hasattr(f_fac, 'seek'): f_fac.seek(0)
    df_ref = pd.read_excel(f_fac, header=idx_ref, dtype=str)
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower()
        if "document" in cl or "n° bon" in cl: cols_ref[c] = "Num Ticket"
        if "q liv" in cl or "poids" in cl: cols_ref[c] = "Poids_Facture"
        if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
        if "date" in cl and "heure" not in cl: cols_ref[c] = "Date_Ref"
        if "immat" in cl: cols_ref[c] = "Immatriculation"
        if "libellé produit" in cl or "libelle produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "chauffeur" in cl or "conducteur" in cl: cols_ref[c] = "Chauffeur"
        
    # Fallback pour fichiers Valoseine sans entête (basé sur l'absence de colonnes nommées)
    if "Date_Ref" not in cols_ref.values() and any("Unnamed" in str(c) for c in df_ref.columns):
        if hasattr(f_fac, 'seek'): f_fac.seek(0)
        df_ref = pd.read_excel(f_fac, header=None, dtype=str)
        df_ref = df_ref.dropna(how='all')
        if len(df_ref.columns) >= 13:
            cols_ref = {
                df_ref.columns[0]: "Date_Ref",
                df_ref.columns[3]: "Num Ticket",
                df_ref.columns[4]: "Chauffeur",
                df_ref.columns[5]: "Immatriculation",
                df_ref.columns[7]: "TEMP_CodeAdresse",
                df_ref.columns[8]: "EXT_Matiere",
                df_ref.columns[9]: "Client_Fournisseur",
                df_ref.columns[12]: "Poids_Facture"
            }
            # Ne garder que les lignes de données en validant la présence de chiffres dans le Poids
            def is_poids_valide(val):
                try: 
                    float(str(val).replace(',', '.'))
                    return True
                except: return False
            mask_valid = df_ref[df_ref.columns[12]].apply(is_poids_valide)
            df_ref = df_ref[mask_valid]

    df_ref = df_ref.rename(columns=cols_ref)
    df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]

    # Gestion des RUPTURES (Code Adresse: ...)
    def extract_rupture(row):
        for v in row:
            s = str(v).strip()
            if s.lower().startswith("code adresse:"):
                return s.split(":", 1)[1].strip()
        return np.nan
    df_ref['_rupture'] = df_ref.apply(extract_rupture, axis=1)
    df_ref['_rupture'] = df_ref['_rupture'].ffill()
    
    if 'TEMP_CodeAdresse' in df_ref.columns:
        df_ref['EXT Client'] = df_ref['TEMP_CodeAdresse'].replace(['', 'nan', 'NAN', 'None'], np.nan).fillna(df_ref['_rupture'])
    else:
        df_ref['EXT Client'] = df_ref['_rupture']
        
    # Nettoyage des lignes vides ou sous-totaux (sans Date ET sans Ticket)
    mask_empty = (
        (df_ref['Num Ticket'].isna() | (df_ref['Num Ticket'].astype(str).str.strip() == '') | (df_ref['Num Ticket'].astype(str).str.lower().isin(['nan', 'nat', 'none']))) &
        (df_ref['Date_Ref'].isna() | (df_ref['Date_Ref'].astype(str).str.strip() == '') | (df_ref['Date_Ref'].astype(str).str.lower().isin(['nan', 'nat', 'none'])))
    )
    df_ref = df_ref[~mask_empty].copy()
    
    # Suppression des lignes de rupture et des sous-totaux
    mask_rupture = df_ref.apply(lambda r: any("code adresse:" in str(v).lower() for v in r), axis=1)
    mask_subtotal = df_ref.apply(lambda r: any(str(v).strip().lower() in ['total', 'sous-total', 'sous total'] or str(v).strip().lower().startswith('total ') for v in r), axis=1)
    df_ref = df_ref[~(mask_rupture | mask_subtotal)].copy()

    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = df_ref["Poids_Facture"].astype(str).str.replace(',', '.')
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
    
    if 'Date_Ref' in df_ref.columns:
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
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN") if 'Date_Ref' in l_ter.columns else "NAN"
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda x: convertir_date_robuste(x).strftime('%Y-%m-%d') if pd.notna(convertir_date_robuste(x)) else "NAN") if 'Date_Ref' in l_ref.columns else "NAN"
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
                    match2['Methode'] = '2. Rapprochement Intelligent'; match2['_merge'] = 'both'
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
    final_orph_t = final_t.rename(columns={c: str(c) + '_T' for c in cols_ter_orig})
    final_orph_f = final_f.rename(columns={c: str(c) + '_F' for c in cols_ref_orig})
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
    
    if 'Date' not in final.columns and 'Date_Ref' in final.columns:
        final = final.rename(columns={'Date_Ref': 'Date'})
    elif 'Date_Ref' in final.columns:
        final['Date'] = final['Date_Ref']
        
    cols_final = ['Date', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
    cols_str = ['Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client']
    
    for c in cols_final:
        if c not in final.columns: final[c] = ""
    
    for c in cols_str:
        if c in final.columns:
            final[c] = final[c].fillna('').astype(str).replace(['nan', 'NAN', 'None', '<NA>', 'NaN'], '')
            
    return final[cols_final]
