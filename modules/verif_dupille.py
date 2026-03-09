import pandas as pd
import numpy as np
import logging
from datetime import datetime
import re
import unicodedata
import streamlit as st

# --- LOGGER ---
logger = logging.getLogger(__name__)

# --- UTILS ---

def convertir_date_robuste(val):
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (datetime, pd.Timestamp)): 
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

def check_site_keys(row):
    k1 = str(row.get('Key_Site_T', '')).strip().upper()
    k2 = str(row.get('Key_Site_F', '')).strip().upper()
    if not k1 or not k2 or k1 == 'NAN' or k2 == 'NAN': return False
    if k1 == k2: return True
    
    ignore_words = {'DECHETTERIE', 'DECHETERIE', 'SMIRTOM', 'SIARE', 'SAINT', 'ST', 'SUR', 'EN', 'LES', 'LE', 'LA', 'DES', 'DE'}
    s1 = set(k1.split()) - ignore_words
    s2 = set(k2.split()) - ignore_words
    
    if not s1 or not s2:
        return False
        
    return not s1.isdisjoint(s2)

def resolve_col(df, base_name):
    res = df.get(base_name, pd.Series(np.nan, index=df.index))
    ct, cf = f"{base_name}_T", f"{base_name}_F"
    if ct in df.columns:
        res = res.fillna(df[ct])
    if cf in df.columns:
        res = res.fillna(df[cf])
    return res

def resolve_multi(df, candidates):
    res = pd.Series(np.nan, index=df.index)
    for cand in candidates:
        for suffix in ['', '_T', '_F']:
            name = f"{cand}{suffix}"
            if name in df.columns:
                # Convert empty strings and other null-like values to NaN before fillna
                clean_col = df[name].copy()
                if clean_col.dtype == object:
                    clean_col = clean_col.replace(r'^\s*$', np.nan, regex=True).replace(['nan', 'NAN', 'None', 'None'], np.nan)
                res = res.fillna(clean_col)
    return res

def normaliser_matiere_dupille(val):
    if pd.isna(val): return ""
    v = str(val).upper().strip()
    # Simplified normalization for matching
    if "BOIS" in v: return "BOIS"
    if "GRAVAT" in v: return "GRAVATS"
    if "DIB" in v or "MELANGE" in v: return "DIB"
    if "CARTON" in v: return "CARTONS"
    if "PLASTIQUE" in v: return "PLASTIQUES"
    if "VÉGÉTAUX" in v or "VEGETAUX" in v: return "DECHETS VERTS"
    if "DÉCHETS VÉGÉTAUX" in v or "DECHETS VEGETAUX" in v: return "DECHETS VERTS"
    if "DECHETS VERTS" in v or "DÉCHETS VERTS" in v: return "DECHETS VERTS"
    return v

def normaliser_client_dupille(val):
    if pd.isna(val): return ""
    v = str(val).upper().strip()
    return normalize_site_key(v)

# --- PROVIDER: DUPILLE ---

def charger_dupille(f):
    try:
        temp = pd.read_excel(f, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num ticket" in row_str and "date" in row_str:
                idx = i; break
        f.seek(0)
        df = pd.read_excel(f, header=idx)
        cols = {}
        for c in df.columns:
            cl = str(c).lower().strip()
            if "num bon" in cl: cols[c] = "Num Bon"
            if "chauffeur" in cl: cols[c] = "Chauffeur"
            if "immatriculation" in cl: cols[c] = "Immatriculation"
            if "description" in cl: cols[c] = "Matiere_T"
            if "num ticket" in cl:
                if "2" in cl: cols[c] = "Num Ticket 2"
                else: cols[c] = "Num Ticket"
            if "nchantier" in cl: cols[c] = "INT Client"
            if "poids" in cl or "tonnes" in cl: cols[c] = "Poids_Terrain"
            if cl in ["date", "le", "journee", "journée"]: cols[c] = "Date_Ref"
            elif "date" in cl and "jour" not in cl: cols[c] = "Date_Ref"
        df = df.rename(columns=cols)
        df = df.loc[:, ~df.columns.duplicated()]
        for txt_col in ["Num Ticket", "Num Ticket 2", "INT Client", "Chauffeur", "Immatriculation", "Matiere_T", "Num Bon"]:
            if txt_col in df.columns:
                df[txt_col] = df[txt_col].astype(str).replace('nan', '')
        if "Poids_Terrain" in df.columns:
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
        df['Date_Ref'] = df['Date_Ref'].apply(convertir_date_robuste)
        return df
    except Exception as e:
        logger.error(f"Erreur charger_dupille: {e}")
        return pd.DataFrame()

def charger_dupille_facture(f_fac):
    try:
        xls = pd.ExcelFile(f_fac)
        all_sheets = []
        for sheet_name in xls.sheet_names:
            df_sample = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=15)
            header_idx = None
            for i, row in df_sample.iterrows():
                row_str = str(row.values).lower()
                if any(k in row_str for k in ['net', 'poids']) and any(k in row_str for k in ['id', 'ticket']):
                    header_idx = i; break
            if header_idx is not None:
                df = pd.read_excel(xls, sheet_name=sheet_name, header=header_idx, dtype=str)
                df = df.dropna(how='all', axis=1)
                df['Original_Sheet_Name'] = str(sheet_name)
                all_sheets.append(df)
            else:
                df = pd.read_excel(xls, sheet_name=sheet_name, header=0, dtype=str)
                df['Original_Sheet_Name'] = str(sheet_name)
                all_sheets.append(df)
        if not all_sheets: return pd.DataFrame()
        return pd.concat(all_sheets, ignore_index=True)
    except Exception as e:
        logger.error(f"Erreur chargement facture Dupille: {e}")
        return pd.DataFrame()

def process_dupille(f_lb, f_fac):
    df_lb = charger_dupille(f_lb)
    if df_lb.empty: return pd.DataFrame()
    if 'Date_Ref' in df_lb.columns:
         j_col = None
         for c in df_lb.columns:
             if str(c).lower().strip() == 'jour': j_col = c; break
         if 'Num Ticket 2' in df_lb.columns and 'Num Ticket' in df_lb.columns:
             df_lb['Num Ticket'] = df_lb['Num Ticket'].fillna(df_lb['Num Ticket 2'])
         elif 'Num Ticket 2' in df_lb.columns and 'Num Ticket' not in df_lb.columns:
             df_lb['Num Ticket'] = df_lb['Num Ticket 2']
         if j_col:
             df_lb[j_col] = df_lb[j_col].astype(str).replace(r'^\s*$', np.nan, regex=True).replace(['nan', 'NaN', 'None'], np.nan)
             df_lb[j_col] = df_lb[j_col].ffill()
    
    df_fac = charger_dupille_facture(f_fac)
    cols_to_drop = [c for c in df_fac.columns if "COLONNE" in str(c).upper()]
    if cols_to_drop: df_fac = df_fac.drop(columns=cols_to_drop)
    nc = {}
    for c in df_fac.columns:
        cl = str(c).lower().strip()
        if "ticket" in cl or cl == "id": nc[c] = "Num Ticket"
        elif "net" in cl or ("poids" in cl and "facture" in cl): nc[c] = "Poids_Facture" 
        elif "zone" in cl or "lib_zone" in cl: nc[c] = "EXT Client"
        elif "client" in cl or "lib_client" in cl: nc[c] = "Ref_Client"
        elif "code matière" in cl or "lib_produit" in cl or "matière" in cl or "produit" in cl: nc[c] = "EXT_Matiere"
        elif "immatriculation" in cl or "véhicule" in cl: nc[c] = "Immatriculation"
        elif "transporteur" in cl or "lib_transporteur" in cl: nc[c] = "Transporteur"
        elif "bordereau" in cl or "bon de" in cl or (cl.startswith("n") and cl.endswith("bon")) or "n° bon" in cl or "num bon" in cl or "bon n" in cl: nc[c] = "Num Bon"
        elif "date" in cl or "dates" in cl or cl in ["le", "journee", "journée"]: nc[c] = "Date_Ref"
        elif "original_sheet_name" in cl: nc[c] = "Activité"
    df_fac = df_fac.rename(columns=nc)
    df_fac = df_fac.loc[:, ~df_fac.columns.duplicated()]
    target_names = ["Num Ticket", "Poids_Facture", "Client", "EXT Client", "EXT_Matiere", "Immatriculation", "Transporteur", "Date_Ref", "Num Bon", "Activité"]
    for target in target_names:
        cols_indices = [j for j, name in enumerate(df_fac.columns) if name == target]
        if len(cols_indices) > 1:
            combined = df_fac.iloc[:, cols_indices[0]].copy()
            for idx in cols_indices[1:]: combined = combined.fillna(df_fac.iloc[:, idx])
            df_fac = df_fac.loc[:, df_fac.columns != target].copy()
            df_fac[target] = combined
    # Nettoyage des sous-totaux et lignes vides (sans Date ET sans Ticket) dans la facture Dupille
    mask_empty = (
        (df_fac['Num Ticket'].isna() | (df_fac['Num Ticket'].astype(str).str.strip() == '') | (df_fac['Num Ticket'].astype(str).str.lower().isin(['nan', 'nat', 'none']))) &
        (df_fac['Date_Ref'].isna() | (df_fac['Date_Ref'].astype(str).str.strip() == '') | (df_fac['Date_Ref'].astype(str).str.lower().isin(['nan', 'nat', 'none'])))
    )
    df_fac = df_fac[~mask_empty].copy()
    
    # Nettoyage supplémentaire par keywords
    mask_subtotal = df_fac.apply(lambda r: any(str(v).strip().lower() in ['total', 'sous-total', 'sous total'] or str(v).strip().lower().startswith('total ') for v in r), axis=1)
    df_fac = df_fac[~mask_subtotal].copy()
    
    # Exclusion des clients "dechetterie professionnel"
    if 'EXT Client' in df_fac.columns:
        mask_pro = df_fac['EXT Client'].astype(str).str.lower().str.contains("dechetterie professionnel", na=False)
        df_fac = df_fac[~mask_pro].copy()
    
    if "Transporteur" in df_fac.columns:
        df_fac['Transporteur'] = df_fac['Transporteur'].astype(str).str.upper()
        df_fac = df_fac[df_fac['Transporteur'].str.contains("SOTREMA", na=False)]
    if "Poids_Facture" in df_fac.columns:
        p = pd.to_numeric(df_fac["Poids_Facture"], errors='coerce').fillna(0)
        if p.mean() > 50: p = p / 1000.0
        df_fac["Poids_Facture"] = p
    if 'Date_Ref' in df_fac.columns: df_fac['Date_Ref'] = df_fac['Date_Ref'].apply(convertir_date_robuste)
    if 'EXT Client' in df_fac.columns: df_fac['EXT Client'] = df_fac['EXT Client'].apply(normaliser_client_dupille)
    if 'EXT_Matiere' in df_fac.columns: df_fac['EXT_Matiere'] = df_fac['EXT_Matiere'].apply(normaliser_matiere_dupille)
    if 'Activité' not in df_fac.columns: df_fac['Activité'] = 'DUPILLE_FAC'
    if 'Num Ticket' in df_fac.columns: df_fac['Num Ticket'] = df_fac['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace(['nan', 'None', '', 'NAN'], np.nan)
    if 'Num Ticket' in df_lb.columns and 'Num Bon' in df_lb.columns:
        clean_lb = df_lb.dropna(subset=['Num Ticket', 'Num Bon']).copy()
        clean_lb['Num Ticket'] = clean_lb['Num Ticket'].astype(str).str.strip(); clean_lb['Num Bon'] = clean_lb['Num Bon'].astype(str).str.strip()
        t_to_b = dict(zip(clean_lb['Num Ticket'], clean_lb['Num Bon']))
        if 'Num Bon' not in df_fac.columns: df_fac['Num Bon'] = np.nan
        def fill_bon(row):
            b = str(row.get('Num Bon', '')).strip().upper()
            if b not in ['', 'NAN', 'NONE', '0']: return row.get('Num Bon')
            t_str = str(row.get('Num Ticket', '')).upper().strip()
            if not t_str or t_str in ['NAN', 'NONE']: return np.nan
            tokens = re.split(r'[ \/,+\-]+', t_str)
            for token in tokens:
                token = token.strip()
                if not token: continue
                found_b = t_to_b.get(token)
                if found_b: return found_b
            return np.nan
        df_fac['Num Bon'] = df_fac.apply(fill_bon, axis=1)

    def aggregate_dupille_df(df, type_suffix):
        if 'Num Bon' not in df.columns: return df
        df = df.loc[:, ~df.columns.duplicated()].copy()
        df['AGG_BON'] = df['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', '', 'NONE'], np.nan)
        mask_bon = df['AGG_BON'].notna(); df_to_agg = df[mask_bon].copy(); df_rest = df[~mask_bon].copy()
        if df_to_agg.empty: return df
        p_col = 'Poids_Terrain' if 'Poids_Terrain' in df.columns else 'Poids_Facture'
        group_cols = ['AGG_BON']; group_cols = [c for c in group_cols if c in df_to_agg.columns]
        agg_rules = {p_col: 'sum', 'Num Ticket': lambda x: ' / '.join(filter(None, [str(v) for v in sorted(list(set(x)))]))}
        for c in df_to_agg.columns:
            if c not in group_cols and c not in agg_rules and c != 'AGG_BON': agg_rules[c] = 'first'
        df_agg = df_to_agg.groupby(group_cols, as_index=False).agg(agg_rules)
        final_df = pd.concat([df_agg, df_rest], ignore_index=True)
        if 'AGG_BON' in final_df.columns: final_df = final_df.drop(columns=['AGG_BON'])
        return final_df

    df_lb = aggregate_dupille_df(df_lb, "_T"); df_fac = aggregate_dupille_df(df_fac, "_F")
    def get_strict_key(row):
        t = str(row.get('Num Ticket', '')).strip().upper()
        if t in ['ST', 'NAN', '', 'NONE', '0', 'None', 'NAT']: return np.nan
        return t
    df_lb['K'] = df_lb.apply(get_strict_key, axis=1); df_fac['K'] = df_fac.apply(get_strict_key, axis=1)
    df_lb['_TMP_ID'] = df_lb.index; df_fac['_TMP_ID'] = df_fac.index
    m1 = pd.merge(df_lb.dropna(subset=['K']), df_fac.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'
    ids_t = match1['K'].unique(); ids_f = match1['K'].unique()
    l_ter = df_lb[~df_lb['K'].isin(ids_t)].copy(); l_ref = df_fac[~df_fac['K'].isin(ids_f)].copy()
    match2 = pd.DataFrame()
    if 'Num Bon' in l_ter.columns and 'Num Bon' in l_ref.columns:
         l_ter['B_K'] = l_ter['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', ''], np.nan)
         l_ref['B_K'] = l_ref['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', ''], np.nan)
         m2 = pd.merge(l_ter.dropna(subset=['B_K']), l_ref.dropna(subset=['B_K']), on='B_K', how='inner', suffixes=('_T', '_F'))
         if not m2.empty:
             match2 = m2.drop_duplicates(subset=['B_K']); match2['Methode'] = '1. Bon Exact'; match2['_merge'] = 'both'
             ids_t2 = match2['_TMP_ID_T'].unique(); ids_f2 = match2['_TMP_ID_F'].unique()
             l_ter = l_ter[~l_ter['_TMP_ID'].isin(ids_t2)]; l_ref = l_ref[~l_ref['_TMP_ID'].isin(ids_f2)]

    match3_smart = pd.DataFrame()
    if not l_ter.empty and not l_ref.empty and 'Poids_Terrain' in l_ter.columns and 'Poids_Facture' in l_ref.columns and 'Date_Ref' in l_ter.columns and 'Date_Ref' in l_ref.columns:
        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "NAN")
        m3 = pd.merge(l_ter[l_ter['Key_Date'] != "NAN"], l_ref[l_ref['Key_Date'] != "NAN"], on='Key_Date', suffixes=('_T', '_F'))
        if not m3.empty:
            m3['Delta'] = abs(pd.to_numeric(m3['Poids_Terrain'], errors='coerce') - pd.to_numeric(m3['Poids_Facture'], errors='coerce'))
            cands = m3[m3['Delta'] <= 0.02].sort_values('Delta')
            if not cands.empty:
                match3_smart = cands.drop_duplicates(subset=['_TMP_ID_T'], keep='first').drop_duplicates(subset=['_TMP_ID_F'], keep='first')
                match3_smart['Methode'] = '2. Rapprochement Intelligent'; match3_smart['_merge'] = 'both'
                ids_t3 = match3_smart['_TMP_ID_T'].unique(); ids_f3 = match3_smart['_TMP_ID_F'].unique()
                l_ter = l_ter[~l_ter['_TMP_ID'].isin(ids_t3)]; l_ref = l_ref[~l_ref['_TMP_ID'].isin(ids_f3)]

    orph_t = l_ter.rename(columns={c: c + '_T' for c in df_lb.columns}); orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    orph_f = l_ref.rename(columns={c: c + '_F' for c in df_fac.columns}); orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    final = pd.concat([match1, match2, match3_smart, orph_t, orph_f], ignore_index=True)
    final['Exutoire'] = "DUPILLE"
    final['Num Ticket'] = resolve_multi(final, ["Num Ticket", "Num Ticket 2"]).fillna('').astype(str)
    final['Num Bon'] = resolve_multi(final, ["Num Bon"]).fillna('').astype(str)
    final['Date_Ref'] = resolve_multi(final, ["Date_Ref"]).fillna(pd.NaT)
    
    p_t = pd.to_numeric(resolve_multi(final, ["Poids_Terrain"]), errors='coerce').fillna(0)
    final['Poids_Terrain'] = p_t
    p_f = pd.to_numeric(resolve_multi(final, ["Poids_Facture"]), errors='coerce').fillna(0)
    final['Poids_Facture'] = p_f
    
    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']

    final['INT Client'] = resolve_multi(final, ["INT Client", "Tournée modèle", "Client"]).fillna('').astype(str)
    final['EXT Client'] = resolve_multi(final, ["EXT Client", "Client", "Ref_Client"]).fillna('').astype(str)
    final['Matiere_T'] = resolve_multi(final, ["Matiere_T"]).fillna('').astype(str)
    final['EXT_Matiere'] = resolve_multi(final, ["EXT_Matiere", "Matiere"]).fillna('').astype(str)

    final['Activité'] = resolve_multi(final, ["Activité"]).fillna("DECH_DUPILLE").astype(str)
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final))); c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final))); c_ch_f = final.get('Chauffeur_F', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f).astype(str).replace(['nan', 'NAN', 'None'], '')
    c_im = final.get('Immatriculation', pd.Series([np.nan]*len(final))); c_im_t = final.get('Immatriculation_T', pd.Series([np.nan]*len(final))); c_im_f = final.get('Immatriculation_F', pd.Series([np.nan]*len(final)))
    final['Immatriculation'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace(['nan', 'NAN', 'None'], '')
    if 'Matiere_T' in final.columns: final['Matiere_T'] = final['Matiere_T'].apply(normaliser_matiere_dupille)
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    
    def check_mat_dupille(row):
        m_t = str(row.get('Matiere_T', '')).upper().strip(); m_f = str(row.get('EXT_Matiere', '')).upper().strip()
        if row['_merge'] == 'left_only': return 'Pb.Mat' if m_t in ['', 'NAN'] else ''
        if row['_merge'] == 'right_only': return 'Pb.Mat' if m_f in ['', 'NAN'] else ''
        if row['_merge'] != 'both': return ''
        if not m_t or m_t == 'NAN': return 'Pb.Mat'
        if m_t == m_f or m_t in m_f or m_f in m_t: return 'OK'
        return 'Pb.Mat'
    final['Verif_Matiere'] = final.apply(check_mat_dupille, axis=1)
    final['Key_Site_T_FINAL'] = final['INT Client'].apply(normalize_site_key)
    final['Key_Site_F_FINAL'] = final['EXT Client'].apply(normalize_site_key)
    
    def check_client_dupille_strict(row):
        k_t = row.get('Key_Site_T_FINAL'); k_f = row.get('Key_Site_F_FINAL')
        c_int = str(row.get('INT Client', '')).upper()
        c_ext = str(row.get('EXT Client', '')).upper()
        
        # Explicit mismatch for Epone vs Vaucouleurs despite sharing the word "DECHETTERIE"
        if ("EPONE" in c_int and "VAUCOULEURS" in c_ext) or ("VAUCOULEURS" in c_int and "EPONE" in c_ext):
            return 'Pb.Clt'
            
        if check_site_keys({'Key_Site_T': k_t, 'Key_Site_F': k_f}): return 'OK'
        
        if any(char.isdigit() for char in c_ext): return "OK"
        if ("GPSEO" in c_int and "GPSO" in c_ext) or ("GPSO" in c_int and "GPSEO" in c_ext): return "OK"
        return 'Pb.Clt'
    final['Verif_Client'] = final.apply(check_client_dupille_strict, axis=1)
    return final
