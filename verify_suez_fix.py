import pandas as pd
import numpy as np
import datetime
import unicodedata
import streamlit as st # Mocking st if needed or removing dependency

# Mock streamlit to avoid errors
class MockSt:
    def error(self, msg): print(f"ERROR: {msg}")
    def warning(self, msg): print(f"WARNING: {msg}")
st = MockSt()

# --- COPIED & ADAPTED FUNCTIONS FROM APP.PY ---

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

def charger_suez_terrain(f, type_fichier):
    try:
        temp = pd.read_excel(f, header=None, nrows=10); idx = 3 
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "num tp manuel" in row_str or "n°bon de vidage" in row_str: idx = i; break
        # Reset file pointer for real read if it was a file object, but here we pass paths so...
        # If passing path, pd.read_excel handles it directly.
        df = pd.read_excel(f, header=idx); cols_map = {}
        
        for c in df.columns:
            cl = str(c).lower().strip()
            if "tp manuel" in cl: cols_map[c] = "Num Ticket"
            elif "bon de vidage" in cl: cols_map[c] = "Num Bon"
            if "quantiteligne" in cl: cols_map[c] = "Poids_Terrain"
            if "description" in cl or "nature" in cl: cols_map[c] = "Matiere_T"
            if "date" in cl: cols_map[c] = "Date_Ref"
            if "immat" in cl or "camion" in cl: cols_map[c] = "Immatriculation"
        
        # Priority mapping for Client
        best_client_col = None
        for c in df.columns:
             cl = str(c).lower().strip()
             if "nchantier" in cl: best_client_col = c; break # Priority 1
        
        if not best_client_col:
             for c in df.columns:
                 cl = str(c).lower().strip()
                 if "exutoire" in cl: best_client_col = c; break # Priority 2

        if best_client_col:
            cols_map[best_client_col] = "Client"

        df = df.rename(columns=cols_map); df = df.loc[:, ~df.columns.duplicated()]
        if 'Num Ticket' in df.columns: df['Num Ticket'] = df['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        df['Activité'] = type_fichier; return df
    except Exception as e: print(f"Erreur chargement {type_fichier}: {e}"); return pd.DataFrame()

DICT_CORRECTION_SUEZ = {
    "CTC MUREAUX": "CTC LES MUREAUX",
    "DECHETTERIE MLJ CLOSEAUX 1": "DECHETERIE DES CLOSEAUX MANTES LA J",
    "DECHETTERIE MLJ CLOSEAUX 2": "DECHETERIE DES CLOSEAUX MANTES LA J",
    "DECHETTERIE MLV VAUCOULEURS": "DECHETTERIE DE LA VAUCOULEURS"
}

def process_suez(f_ctc, f_dech, f_fac):
    dfs = []
    # Passing paths directly
    if f_ctc: dfs.append(charger_suez_terrain(f_ctc, "CTC"))
    if f_dech: dfs.append(charger_suez_terrain(f_dech, "DECH"))
    if not dfs: return pd.DataFrame()
    df_ter = pd.concat(dfs, ignore_index=True)
    if 'Poids_Terrain' not in df_ter.columns: df_ter['Poids_Terrain'] = 0
    if 'Poids_Terrain' not in df_ter.columns: df_ter['Poids_Terrain'] = 0
    df_ref = pd.read_excel(f_fac, header=0)
    print(f"DEBUG: Columns in Listing: {df_ref.columns.tolist()}")
    
    # Filtrage Client GPSEOAUB
    col_client_filter = None
    for c in df_ref.columns:
        if "nom recherche client" in str(c).lower(): col_client_filter = c; break
    
    if col_client_filter:
        count_before = len(df_ref)
        # Debug specific ticket before filtering
        debug_ticket = "PRC591307"
        found = df_ref[df_ref.astype(str).apply(lambda x: x.str.contains(debug_ticket, case=False)).any(axis=1)]
        if not found.empty:
             print(f"DEBUG RAW: Found {debug_ticket} in raw file. Client Value: {found[col_client_filter].values}")
        else:
             print(f"DEBUG RAW: {debug_ticket} NOT found in raw file.")

        df_ref = df_ref[df_ref[col_client_filter].astype(str).str.upper().str.strip() == "GPSEOAUB"]
        print(f"DEBUG: Filtered GPSEOAUB. Rows: {count_before} -> {len(df_ref)}")
    
    cols_ref = {}
    for c in df_ref.columns:
        cl = str(c).lower().strip()
        if "n° bon de pesée" in cl: cols_ref[c] = "Num Ticket"
        if "quantité nette" in cl: cols_ref[c] = "Poids_Facture"
        if "date du bon" in cl: cols_ref[c] = "Date_Ref"
        if "nom de l'adresse de service" in cl: 
            print(f"DEBUG: Found Service Address col: {c}")
            cols_ref[c] = "EXT Client"
        if "description déchet" in cl: cols_ref[c] = "EXT_Matiere"
        if "immatriculation" in cl: cols_ref[c] = "Immatriculation"
        
    for c in df_ref.columns:
         cl = str(c).lower().strip()
         if "nom recherche client" in cl and "EXT Client" not in cols_ref.values(): 
             print(f"DEBUG: Fallback to Search Client col: {c}")
             cols_ref[c] = "EXT Client" # Fallback

    df_ref = df_ref.rename(columns=cols_ref); df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]
    if 'Num Ticket' in df_ref.columns: df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True)
    if 'Poids_Facture' in df_ref.columns: df_ref['Poids_Facture'] = pd.to_numeric(df_ref['Poids_Facture'], errors='coerce') / 1000
    df_ter['K'] = df_ter['Num Ticket'].astype(str).str.strip(); df_ref['K'] = df_ref['Num Ticket'].astype(str).str.strip()
    
    # DEBUG: Check for dropped rows
    dropped_ter = len(df_ter[df_ter['K'] == 'nan'])
    if dropped_ter > 0:
        print(f"\nDEBUG CRITICAL: Dropping {dropped_ter} Terrain rows with Missing Ticket Number!")
        print(df_ter[df_ter['K'] == 'nan'][['Num Bon', 'Poids_Terrain', 'Date_Ref']].head())
                                               
    df_ter = df_ter[df_ter['K'] != 'nan']; df_ref = df_ref[df_ref['K'] != 'nan']; cols_ter = df_ter.columns.tolist(); cols_ref = df_ref.columns.tolist()
    m1 = pd.merge(df_ter, df_ref, on='K', how='outer', indicator=True, suffixes=('_T', '_F')); match1 = m1[m1['_merge'] == 'both'].copy(); left1 = m1[m1['_merge'] == 'left_only'].copy(); right1 = m1[m1['_merge'] == 'right_only'].copy()
    
    # --- SECONDE PASSE : AUTO-MATCH (Date + Poids + Matière Apprise) ---
    match1['Methode'] = '1. Ticket'
    
    # 1. Apprentissage Dictionnaire Matières
    pairs = match1[['Matiere_T', 'EXT_Matiere']].dropna().drop_duplicates()
    dict_matiere_learned = {}
    for i, r in pairs.iterrows():
        t_mat = str(r['Matiere_T']).strip().upper()
        f_mat = str(r['EXT_Matiere']).strip().upper()
        if t_mat and f_mat:
            dict_matiere_learned[t_mat] = f_mat
            
    print(f"DEBUG: Learned {len(dict_matiere_learned)} material mappings.")

    # 2. Préparation Leftovers
    print(f"DEBUG: Leftovers - Terrain: {len(left1)}, Facture: {len(right1)}")
    l_ter = restore_columns(left1, '_T', cols_ter)
    l_ref = restore_columns(right1, '_F', cols_ref)
    
    if not l_ter.empty and not l_ref.empty:
        # Helper keys
        def get_date_key(d):
            val = convertir_date_robuste(d)
            return val.strftime('%Y-%m-%d') if pd.notna(val) else "NAN"
        
        def get_weight_key(w):
            try: return "{:.2f}".format(float(w))
            except: return "0.00"
            
        def normalize_matiere_heuristique(m):
            m_upper = str(m).strip().upper()
            if "DIB" in m_upper: return "DIB"
            if "GRAVAT" in m_upper: return "GRAVATS"
            if "BOIS" in m_upper: return "BOIS"
            if "VEGETA" in m_upper: return "VEGETAUX"
            if "ENCOMBRANT" in m_upper: return "ENCOMBRANTS"
            if "TODO" in m_upper: return "TOUT VENANT"
            return m_upper

        def get_mat_key_ter(m):
            m_clean = str(m).strip().upper()
            # 1. Learned Dictionary
            if m_clean in dict_matiere_learned:
                 mapped = dict_matiere_learned[m_clean]
                 return normalize_matiere_heuristique(mapped)
            # 2. Heuristic
            return normalize_matiere_heuristique(m_clean)

        def get_mat_key_ref(m):
            return normalize_matiere_heuristique(str(m).strip().upper())

        l_ter['Key_Date'] = l_ter['Date_Ref'].apply(get_date_key)
        l_ter['Key_Weight'] = l_ter['Poids_Terrain'].apply(get_weight_key)
        l_ter['Key_Mat'] = l_ter['Matiere_T'].apply(get_mat_key_ter)
        
        l_ref['Key_Date'] = l_ref['Date_Ref'].apply(get_date_key)
        l_ref['Key_Weight'] = l_ref['Poids_Facture'].apply(get_weight_key)
        l_ref['Key_Mat'] = l_ref['EXT_Matiere'].apply(get_mat_key_ref)

        l_ter_filt = l_ter[l_ter['Key_Weight'] != "0.00"]
        l_ref_filt = l_ref[l_ref['Key_Weight'] != "0.00"]

        m2 = pd.merge(l_ter_filt, l_ref_filt, on=['Key_Date', 'Key_Weight', 'Key_Mat'], how='inner', suffixes=('_T', '_F'))
        
        # Identification matchés et restants
        l_ter['UID_T'] = range(len(l_ter)); l_ref['UID_F'] = range(len(l_ref))
        m2_uid = pd.merge(l_ter_filt.reset_index(), l_ref_filt.reset_index(), on=['Key_Date', 'Key_Weight', 'Key_Mat'], how='inner', suffixes=('_T', '_F'))
        
        matched_idx_t = m2_uid['index_T'].tolist()
        matched_idx_f = m2_uid['index_F'].tolist()
        
        match2 = m2.copy()
        match2['Methode'] = '2. Auto'
        # Important: Pour les matchs auto, on écrase le Num Ticket du terrain (souvent erroné) par celui de la facture
        if 'Num Ticket_F' in match2.columns:
             match2['Num Ticket'] = match2['Num Ticket_F']

        print(f"DEBUG: Secondary match found {len(match2)} rows.")
        
        final_left_t = l_ter.drop(matched_idx_t)
        final_left_f = l_ref.drop(matched_idx_f)
    else:
        match2 = pd.DataFrame()
        final_left_t = l_ter
        final_left_f = l_ref

    # --- TROISIEME PASSE : MATCH PAR NUM BON (Terrain) == NUM TICKET (Facture) ---
    # Souvent le Bon de Vidage Terrain correspond au Num Ticket Facture
    
    match3 = pd.DataFrame()
    if not final_left_t.empty and not final_left_f.empty and 'Num Bon' in final_left_t.columns:
        print("DEBUG: Attempting Bon-Ticket Match...")
        # Prepare join keys
        final_left_t['Key_Bon'] = final_left_t['Num Bon'].astype(str).str.strip().str.upper()
        # Invoice Ticket is implicitly the Key 'K' or 'Num Ticket'
        # Check column name in leftovers. Since restore_columns keeps original names:
        # Invoice original 'Num Ticket' column is likely mapped to 'Num Ticket' in cols_ref, 
        # so it should be in final_left_f['Num Ticket']
        
        # Verify invoice ticket col
        inv_ticket_col = 'Num Ticket'
        if inv_ticket_col not in final_left_f.columns: print("DEBUG: Num Ticket not found in Invoice leftovers")
        
        if inv_ticket_col in final_left_f.columns:
             final_left_f['Key_Ticket'] = final_left_f[inv_ticket_col].astype(str).str.strip().str.upper()
             
             # Merge
             m3 = pd.merge(final_left_t, final_left_f, left_on='Key_Bon', right_on='Key_Ticket', how='inner', suffixes=('_T', '_F'))
             
             if not m3.empty:
                 match3 = m3.copy()
                 match3['Methode'] = '3. Bon-Ticket'
                 
                 # Overwrite Ticket with Invoice Ticket
                 if 'Num Ticket_F' in match3.columns:
                     match3['Num Ticket'] = match3['Num Ticket_F']
                 else:
                     match3['Num Ticket'] = match3['Key_Ticket'] # Fallback
                     
                 print(f"DEBUG: Bon-Ticket match found {len(match3)} rows.")
                 
                 # Remove matched from leftovers
                 # Note: merge produces new dataframe, need to track indices to drop
                 # Relying on Key uniqueness might be risky if duplicates exist, but let's try strict index drop if possible or just filter
                 # Using the Key is easier for drop if Unique
                 
                 matched_bons = match3['Key_Bon'].tolist()
                 matched_tickets = match3['Key_Ticket'].tolist()
                 
                 final_left_t = final_left_t[~final_left_t['Key_Bon'].isin(matched_bons)]
                 final_left_f = final_left_f[~final_left_f['Key_Ticket'].isin(matched_tickets)]

    
    final_orph_t = final_left_t.rename(columns={c: c + '_T' for c in cols_ter})
    final_orph_f = final_left_f.rename(columns={c: c + '_F' for c in cols_ref})
    
    merged = pd.concat([match1, match2, match3, final_orph_t, final_orph_f], ignore_index=True); merged['Exutoire'] = "SUEZ"
    
    # Correction poids : prendre Poids_Terrain si existe, sinon Poids_Terrain_T, sinon 0
    p_ter = pd.to_numeric(merged.get('Poids_Terrain', np.nan), errors='coerce')
    p_ter_t = pd.to_numeric(merged.get('Poids_Terrain_T', np.nan), errors='coerce')
    merged['Poids_Terrain'] = p_ter.fillna(p_ter_t).fillna(0)
    
    p_fac = pd.to_numeric(merged.get('Poids_Facture', np.nan), errors='coerce')
    p_fac_f = pd.to_numeric(merged.get('Poids_Facture_F', np.nan), errors='coerce')
    merged['Poids_Facture'] = p_fac.fillna(p_fac_f).fillna(0)
    
    merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
    def resolve(df, col):
        if col in df.columns: res = df[col]
        else: res = pd.Series([np.nan]*len(df), index=df.index)
        c_t, c_f = f"{col}_T", f"{col}_F"
        if c_t in df.columns: res = res.fillna(df[c_t])
        if c_f in df.columns: res = res.fillna(df[c_f])
        return res
    merged['Date'] = resolve(merged, 'Date_Ref').apply(convertir_date_robuste); merged['Num Ticket'] = resolve(merged, 'Num Ticket'); merged['Num Bon'] = resolve(merged, 'Num Bon'); merged['Immatriculation'] = resolve(merged, 'Immatriculation'); 
    
    # Gestion Clients
    c_int = resolve(merged, 'Client'); merged['INT Client'] = c_int.fillna("CU GPSO") # Default if missing
    merged['Client'] = merged['INT Client']
    merged['EXT Client'] = merged.get('EXT Client', merged.get('EXT Client_F', ''))

    merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'}); merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.02).replace({True:'OK', False:'Pb.T'})
    
    def check_client_suez(row):
        try:
            ext_c = str(row.get('EXT Client', '')).strip().upper()
            int_c = str(row.get('INT Client', '')).strip().upper()
            if not ext_c or not int_c: return "OK"
            
            # 1. Dictionnaire
            expected = DICT_CORRECTION_SUEZ.get(int_c)
            if expected:
                if expected == int_c: # If mapped to itself or simple correction
                     if expected in ext_c: return "OK"
                else: # Mapped to something else
                     if expected in ext_c: return "OK"
            
            # 2. Correspondance directe
            if int_c == ext_c: return "OK"
            if int_c in ext_c or ext_c in int_c: return "OK"
            
            return "Pb.Clt"
        except: return "OK"

    merged['Verif_Client'] = merged.apply(check_client_suez, axis=1); merged['Verif_Matiere'] = "OK"; cols_final = ['Date', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket', 'Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 'Methode', 'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
    for c in cols_final:
        if c not in merged.columns: merged[c] = ""
    # Debug Leftovers
    print("\n--- LEFTOVER INSPECTION ---")
    if not l_ter_filt.empty:
         print("Top 10 Terrain Leftovers Keys (Date, Weight, Mat):")
         print(l_ter_filt[['Key_Date', 'Key_Weight', 'Key_Mat', 'Matiere_T', 'Poids_Terrain']].head(10))
    if not l_ref_filt.empty:
         print("\nTop 10 Invoice Leftovers Keys (Date, Weight, Mat):")
         print(l_ref_filt[['Key_Date', 'Key_Weight', 'Key_Mat', 'EXT_Matiere', 'Poids_Facture']].head(10))

    print("\n--- SPECIFIC DEBUG: PRC591307 ---")
    # Check Invoice
    if 'Num Ticket' in l_ref_filt.columns:
         target = l_ref_filt[l_ref_filt['Num Ticket'] == 'PRC591307']
    else:
         target = pd.DataFrame()
        
    
    if not target.empty:
        print("Found matching Invoice row in leftovers:")
        print(target[['Key_Date', 'Key_Weight', 'Key_Mat', 'EXT_Matiere', 'Poids_Facture', 'EXT Client']])

        
        # Check for Terrain candidates with weight 4.56
        w_target = "4.56"
        candidates = l_ter_filt[l_ter_filt['Key_Weight'] == w_target]
        print(f"\nTerrain rows with Key_Weight={w_target}:")
        if not candidates.empty:
             print(candidates[['Key_Date', 'Key_Weight', 'Key_Mat', 'Matiere_T', 'Poids_Terrain', 'Client']])
        else:
             print("No Terrain rows found with EXACT weight 4.56")
             
             # Loose Search
             print("\n--- Loose Search ---")
             # Try date match 2026-01-04
             loose_date = l_ter_filt[l_ter_filt['Key_Date'] == '2026-01-04']
             if not loose_date.empty:
                 print("Terrain rows on 2026-01-04:")
                 print(loose_date[['Key_Date', 'Key_Weight', 'Key_Mat', 'Poids_Terrain', 'Matiere_T', 'Client']])
             else:
                 print("No Terrain rows on 2026-01-04")
                 
             # Try weight range 4.50 - 4.60
             loose_weight = l_ter[l_ter['Poids_Terrain'].between(4.50, 4.60)]
             if not loose_weight.empty:
                 print("Terrain rows with weight between 4.50 and 4.60:")
                 print(loose_weight[['Key_Date', 'Poids_Terrain', 'Matiere_T', 'Client']])
             else:
                 print("No Terrain rows with weight between 4.50 and 4.60")
    else:
        print("Ticket PRC591307 not found in Leftovers (maybe it was matched in Primary?)")

         
    return merged[cols_final]

# --- EXECUTION ---

file_ctc = '/home/amine/projects/verif_exutoire/source/SUEZ/SUEZ_CTC_S2S5_JAN2026.xls'
file_dech = '/home/amine/projects/verif_exutoire/source/SUEZ/SUEZ_DECH_S2S5_JAN2026.xlsx'
file_listing = '/home/amine/projects/verif_exutoire/source/SUEZ/Listing GPSEO du 01 au 11-01-26.xlsx'

print("Processing SUEZ files...")
result = process_suez(file_ctc, file_dech, file_listing)
print(f"Processed {len(result)} lines.")

# Filter for relevant cases
targets = ["CTC MUREAUX", "CTC LES MUREAUX", "CLOSEAUX", "VAUCOULEURS"]
filtered = result[result['INT Client'].astype(str).str.contains('|'.join(targets), case=False, na=False) | result['EXT Client'].astype(str).str.contains('|'.join(targets), case=False, na=False)]

print("\n--- Verification Results (Targeted) ---")
print(filtered[['Num Ticket', 'Num Bon', 'Methode', 'INT Client', 'EXT Client', 'Verif_Client']].head(20))

# Count Pb.Clt
errors = result[result['Verif_Client'] == 'Pb.Clt']
print(f"\nTotal Client Errors: {len(errors)}")
if not errors.empty:
    print("Example Errors (First 10):")
    # Force full display
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(errors[['Num Ticket', 'INT Client', 'EXT Client']].head(10))


orphans = result[result['Verif_Exutoire'] != 'OK']
if not orphans.empty:
    print(orphans[['Num Ticket', 'Poids_Terrain', 'Poids_Facture', 'Ecart']].head(10))
