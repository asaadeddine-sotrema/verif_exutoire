import pandas as pd
import numpy as np
import logging
from datetime import datetime
import re
import unicodedata

# --- LOGGER ---
logger = logging.getLogger(__name__)

# --- UTILS (Shared logic) ---

def convertir_date_robuste(val):
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

def resolve_col(df, base_name):
    if base_name in df.columns: return df[base_name]
    ct, cf = f"{base_name}_T", f"{base_name}_F"
    if ct in df.columns and cf in df.columns:
        return df[ct].fillna(df[cf])
    if ct in df.columns: return df[ct]
    if cf in df.columns: return df[cf]
    return pd.Series([np.nan]*len(df))

# --- PROVIDER: AZALYS ---

def charger_azalys(f, source_name="AZALYS"):
    try:
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
    df_ter = charger_azalys(f_ter, provider_name)
    if df_ter.empty: return pd.DataFrame()
    
    df_ref = pd.read_excel(f_fac, dtype=str)
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "numéro de ticket" in cl: cols_ref[c] = "Num Ticket"
        if "net" in cl: cols_ref[c] = "Poids_Facture"
        if "date du poids" in cl and "entrée" in cl: cols_ref[c] = "Date_Ref"
        if "libellé tiers" in cl: cols_ref[c] = "Client"
        if "libellé produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "unité" in cl: cols_ref[c] = "Unite"
        if "immat" in cl or "véhicule" in cl: cols_ref[c] = "Immatriculation"

    df_ref = df_ref.rename(columns=cols_ref)
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce') / 1000.0
    if 'Date_Ref' in df_ref.columns:
         df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date

    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE', 'ST'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'
    ids_t = match1['K'].unique(); ids_f = match1['K'].unique()
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy(); l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
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
                 match2['Methode'] = '2. Smart Match'; match2['_merge'] = 'both'
                 matched_tickets_f = match2['Num Ticket_F'].tolist()
                 l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str)
                 l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str)
                 uids = match2['UID_T'].unique()
                 l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T'])
                 match2 = match2.drop(columns=['UID_T'])

    cols_t = df_ter.columns; cols_f = df_ref.columns
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t}); orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f}); orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    
    if 'Num Ticket_F' in final.columns: final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else: final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
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
    final['Activité'] = provider_name; final['Exutoire'] = provider_name
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"

    def check_cl(row):
        i = str(row.get('INT Client','')).upper().strip(); e = str(row.get('EXT Client','')).upper().strip()
        if not i or not e: return "OK"
        if i == e: return "OK"
        if normalize_site_key(i) == normalize_site_key(e): return "OK"
        if provider_name == "AZALYS SOTREMA" and "TRIEL" not in i: return "OK"
        k1 = normalize_site_key(i); k2 = normalize_site_key(e)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        return "Pb.Clt"
    final['Verif_Client'] = final.apply(check_cl, axis=1)
    return final

# --- PROVIDER: VALOSEINE ENC ---

def charger_valoseine_enc(f):
    try:
        df = pd.read_excel(f, header=None)
        data = []
        for i, row in df.iterrows():
            if len(row) > 6:
                ticket_val = str(row[6]).strip().upper()
                if (ticket_val.startswith("PRC") or ticket_val.startswith("TM")) and len(ticket_val) > 4:
                    r_date = row[0]; r_client = row[2]; r_poids = row[9] if len(row) > 9 else 0
                    data.append({
                        "Date_Ref": r_date, "Client": r_client, "Num Ticket": ticket_val, "Poids_Terrain": r_poids,
                        "Num Bon": str(row[5]).replace(".0","") if len(row) > 5 else "", 
                        "Matiere_T": row[8] if len(row) > 8 else "",
                        "Chauffeur": str(row[3]).replace("nan", "") if len(row) > 3 else "",
                        "Immat": str(row[4]).replace("nan", "") if len(row) > 4 else ""
                    })
        new_df = pd.DataFrame(data)
        if "Poids_Terrain" in new_df.columns: new_df["Poids_Terrain"] = pd.to_numeric(new_df["Poids_Terrain"], errors='coerce')
        new_df['Activité'] = "ENCOMBRANTS"
        if 'Date_Ref' in new_df.columns: new_df['Date_Ref'] = pd.to_datetime(new_df['Date_Ref'], errors='coerce').dt.date
        return new_df
    except Exception as e:
        logger.error(f"Erreur chargement Valoseine ENC: {e}"); return pd.DataFrame()

def process_valoseine_enc(f_ter, f_fac):
    logger.info("Début traitement VALOSEINE ENC GPSEO")
    df_ter = charger_valoseine_enc(f_ter)
    if df_ter.empty: return pd.DataFrame()
    df_ref = pd.read_excel(f_fac, dtype=str)
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° bon de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "quantité nette" in cl: cols_ref[c] = "Poids_Facture"
        if "date du bon" in cl: cols_ref[c] = "Date_Ref"
        if "nom recherche producteur" in cl: cols_ref[c] = "Producteur"
        if "ville de l'adresse de service" in cl: cols_ref[c] = "Client"
        if "description déchet" in cl: cols_ref[c] = "EXT_Matiere"
        if "nom du transporteur" in cl: cols_ref[c] = "Transporteur"
        if "immat" in cl or "véhicule" in cl: cols_ref[c] = "Immat"
    df_ref = df_ref.rename(columns=cols_ref)
    if 'Producteur' in df_ref.columns and 'Transporteur' in df_ref.columns:
        df_ref = df_ref[(df_ref['Producteur'].astype(str).str.strip().str.upper() == 'VALOOU47') & (df_ref['Transporteur'].astype(str).str.strip().str.upper() == 'SOTREMA')]
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce') / 1000.0
    if 'Date_Ref' in df_ref.columns: df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date
    if 'Num Ticket' in df_ter.columns: df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip().str.upper().replace(['NAN', '', 'NONE'], np.nan)
    m1 = pd.merge(df_ter.dropna(subset=['K']), df_ref.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'
    ids_t = match1['K'].unique(); ids_f = match1['K'].unique()
    l_ter = df_ter[~df_ter['K'].isin(ids_t)].copy(); l_ref = df_ref[~df_ref['K'].isin(ids_f)].copy()
    
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
                 match2['Methode'] = '2. Smart Match'; match2['_merge'] = 'both'
                 matched_tickets_f = match2['Num Ticket_F'].tolist(); l_ref = l_ref[~l_ref['Num Ticket'].isin(matched_tickets_f)]
                 match2['UID_T'] = match2['Key_Date'] + "_" + match2['Poids_Terrain'].astype(str); l_ter['UID_T'] = l_ter['Key_Date'] + "_" + l_ter['Poids_Terrain'].astype(str); uids = match2['UID_T'].unique()
                 l_ter = l_ter[~l_ter['UID_T'].isin(uids)].drop(columns=['UID_T']); match2 = match2.drop(columns=['UID_T'])

    cols_t = df_ter.columns; cols_f = df_ref.columns
    orph_t = l_ter.rename(columns={c: c + '_T' for c in cols_t}); orph_t['_merge'] = 'left_only'; orph_t['Methode'] = 'Non Trouvé'
    orph_f = l_ref.rename(columns={c: c + '_F' for c in cols_f}); orph_f['_merge'] = 'right_only'; orph_f['Methode'] = 'Non Trouvé'
    final = pd.concat([match1, match2, orph_t, orph_f], ignore_index=True)
    if 'Num Ticket_F' in final.columns: final['Num Ticket'] = final['Num Ticket_F'].fillna(final.get('Num Ticket_T')).fillna('').astype(str)
    else: final['Num Ticket'] = resolve_col(final, 'Num Ticket').fillna('').astype(str)
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
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final))); c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final))); c_ch_f = final.get('Chauffeur_F', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).fillna(c_ch_f).astype(str).replace('nan', '')
    c_im = final.get('Immat', pd.Series([np.nan]*len(final))); c_im_t = final.get('Immat_T', pd.Series([np.nan]*len(final))); c_im_f = final.get('Immat_F', pd.Series([np.nan]*len(final)))
    final['Immat'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace('nan', '')
    final['Activité'] = "ENCOMBRANTS"; final['Exutoire'] = "VALOSEINE ENC GPSEO"
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"

    def check_cl(row):
        i = str(row.get('INT Client','')).upper().strip(); e = str(row.get('EXT Client','')).upper().strip()
        if not i or not e: return "OK"
        if i == e: return "OK"
        if normalize_site_key(i) == normalize_site_key(e): return "OK"
        k1 = normalize_site_key(i); k2 = normalize_site_key(e)
        if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
        s1 = set(k1.split()); s2 = set(k2.split())
        if s1.intersection(s2): return "OK"
        return "Pb.Clt"
    final['Verif_Client'] = final.apply(check_cl, axis=1)
    return final
