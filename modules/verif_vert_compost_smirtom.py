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
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]:
        try: return datetime.strptime(s, fmt)
        except: continue
    return pd.to_datetime(val, errors='coerce')

def resolve_col(df, base_name):
    if base_name in df.columns: return df[base_name]
    ct, cf = f"{base_name}_T", f"{base_name}_F"
    if ct in df.columns and cf in df.columns:
        return df[ct].fillna(df[cf])
    if ct in df.columns: return df[ct]
    if cf in df.columns: return df[cf]
    return pd.Series([np.nan]*len(df))

# --- PROVIDER: SMIRTOM VERT COMPOST ---

def charger_vert_compost_smirtom(f):
    try:
        df = pd.read_excel(f, header=None)
        data = []
        for i, row in df.iterrows():
            if len(row) > 6:
                ticket_val = str(row[6]).strip().upper()
                if (ticket_val.startswith("PRC") or ticket_val.startswith("TM")) and len(ticket_val) > 4:
                    r_date = row[0]
                    data.append({
                        "Date_Ref": r_date,
                        "Num Ticket": ticket_val,
                        "Poids_Terrain": row[9],
                        "Client": str(row[2]).strip() if len(row) > 2 else "",
                        "Immat": str(row[4]).strip() if len(row) > 4 else "",
                        "Num Bon": str(row[5]).strip().replace(".0","") if len(row) > 5 else "",
                        "Chauffeur": str(row[3]).strip() if len(row) > 3 else "",
                        "Matiere_T": str(row[8]).strip() if len(row) > 8 else ""
                    })
                    
        new_df = pd.DataFrame(data)
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
    df_ter = charger_vert_compost_smirtom(f_ter)
    if df_ter.empty: return pd.DataFrame()
    
    df_ref = pd.read_excel(f_fac, dtype=str)
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "ticket n°" in cl or "numéro de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "net (kg)" in cl: cols_ref[c] = "Poids_Facture" 
        elif "quantité" in cl and "net" not in cl: cols_ref[c] = "Poids_Facture"
        if "matricule" in cl or "immatriculation" in cl: cols_ref[c] = "Immat"
        if "date" in cl and "sortie" not in cl: cols_ref[c] = "Date_Ref"
        if "produit" in cl: cols_ref[c] = "EXT_Matiere"
        if "client" in cl: cols_ref[c] = "EXT Client"

    df_ref = df_ref.rename(columns=cols_ref)
    if "Poids_Facture" in df_ref.columns:
        df_ref["Poids_Facture"] = pd.to_numeric(df_ref["Poids_Facture"], errors='coerce')
        mean_val = df_ref["Poids_Facture"].mean()
        if mean_val > 50:
             df_ref["Poids_Facture"] = df_ref["Poids_Facture"] / 1000.0
        
    if 'Date_Ref' in df_ref.columns:
         df_ref['Date_Ref'] = pd.to_datetime(df_ref['Date_Ref'], errors='coerce').dt.date

    if 'Num Ticket' in df_ter.columns:
        df_ter['Num Ticket'] = df_ter['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'Num Ticket' in df_ref.columns:
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        df_ref = df_ref[df_ref['Num Ticket'] != '']

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
    c_int = final.get('Client', pd.Series([np.nan]*len(final))); c_int_t = final.get('Client_T', pd.Series([np.nan]*len(final)))
    final['INT Client'] = c_int.fillna(c_int_t).astype(str).replace('nan', '')
    c_ext = final.get('EXT Client', pd.Series([np.nan]*len(final))); c_ext_f = final.get('EXT Client_F', pd.Series([np.nan]*len(final)))
    final['EXT Client'] = c_ext.fillna(c_ext_f).astype(str).replace('nan', '')
    final['Ecart'] = final['Poids_Terrain'] - final['Poids_Facture']
    c_im = final.get('Immat', pd.Series([np.nan]*len(final))); c_im_t = final.get('Immat_T', pd.Series([np.nan]*len(final))); c_im_f = final.get('Immat_F', pd.Series([np.nan]*len(final)))
    final['Immat'] = c_im.fillna(c_im_t).fillna(c_im_f).astype(str).replace('nan', '')
    c_nb = final.get('Num Bon', pd.Series([np.nan]*len(final))); c_nb_t = final.get('Num Bon_T', pd.Series([np.nan]*len(final)))
    final['Num Bon'] = c_nb.fillna(c_nb_t).astype(str).replace('nan', '')
    c_ch = final.get('Chauffeur', pd.Series([np.nan]*len(final))); c_ch_t = final.get('Chauffeur_T', pd.Series([np.nan]*len(final)))
    final['Chauffeur'] = c_ch.fillna(c_ch_t).astype(str).replace('nan', '')
    final['Activité'] = "DECHETS VEGETAUX"; final['Exutoire'] = "VERT COMPOST SMIRTOM"
    final['Verif_Exutoire'] = np.where(final['_merge'] == 'both', 'OK', 'Pb.Ext')
    final['Verif_Tonnes'] = (abs(final['Ecart']) < 0.05).replace({True:'OK', False:'Pb.T'})
    final['Verif_Matiere'] = "OK"; final['Verif_Client'] = "OK"
    return final
