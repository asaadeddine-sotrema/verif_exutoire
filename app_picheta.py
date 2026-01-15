import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os
import numpy as np
import unicodedata
import warnings
from tkcalendar import DateEntry 
import datetime

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
FICHIER_SORTIE = r"\\app\Commun\aminesaadeddine\verif_tonnage_valene\test.csv"
DOSSIER_OUTPUT = "output"

# =============================================================================
# 1. UTILITAIRES
# =============================================================================

def nettoyer_texte(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def clean_plate(texte):
    if pd.isna(texte): return ""
    # On garde alphanum et on met en majuscules
    txt = str(texte).upper().strip()
    return ''.join(c for c in txt if c.isalnum())

def clean_client_match(name):
    if pd.isna(name): return ""
    n = str(name).upper().strip()
    
    # Gestion des synonymes connus (Extraits de verifier_client local)
    if "CLOSEAUX" in n: return "CLOSEAUX"
    if "VAUCOULEURS" in n: return "VAUCOULEURS"
    if "GARGENVILLE" in n: return "GARGENVILLE"
    if "LIMAY" in n: return "LIMAY"
    if "AUBERGENVILLE" in n: return "AUBERGENVILLE"
    if "MUREAUX" in n: return "MUREAUX"
    if "EPONE" in n: return "EPONE"
    if "CONFLANS" in n: return "CONFLANS"
    if "ACHERES" in n: return "ACHERES"
    if "ORGEVAL" in n: return "ORGEVAL"
    if "POISSY" in n: return "POISSY"
    if "TRIEL" in n: return "TRIEL"
    if "CARRIERES" in n: return "CARRIERES"
    
    # Nettoyage générique
    n = n.replace('DECHETTERIE', '').replace('PICHETA', '').replace('MLV', '').replace('MLJ', '')
    return ''.join(c for c in n if c.isalnum())

def check_client_compatibility(row, col_int, col_ext):
    """
    Vérifie si le client interne (Dechetterie) correspond au client externe (Code Adresse).
    Retourne True si match OK, False sinon.
    """
    # Récupération sécurisée des valeurs
    val_int = row.get(col_int, "")
    val_ext = row.get(col_ext, "")
    
    # Si les colonnes n'existent pas ou sont vides, on considère ça comme "Inconnu" -> On ne peut pas invalider sur cette base ?
    # Le user dit "si la dechetterie NE CORRESPOND PAS". 
    # Si on a pas l'info, on laisse passer le match technique (Ticket/Date...)
    if pd.isna(val_int) or str(val_int).strip() == "": return True
    if pd.isna(val_ext) or str(val_ext).strip() == "": return True
    
    c_int = clean_client_match(val_int)
    c_ext = clean_client_match(val_ext)
    
    if not c_int or not c_ext: return True # Trop vide pour décider
    
    # 1. Égalité stricte normalisée
    if c_int == c_ext: return True
    
    # 2. Inclusion
    if c_int in c_ext or c_ext in c_int: return True
    
    # Sinon KO
    return False


def normaliser_matiere(valeur_origine):
    val = nettoyer_texte(valeur_origine)
    if any(x in val for x in ["TRANSPORTS GRAVATS", "GRAVATS"]): return "GRAVATS"
    if "TERRE" in val: return "TERRE"
    if "DIB" in val: return "DIB"
    return val

def convertir_date_robuste(val):
    if pd.isna(val) or val == "":
        return pd.NaT
    
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime.date):
        return val

    try:
        val_num = float(val)
        if val_num > 30000:
            return pd.to_datetime(val_num, unit='D', origin='1899-12-30').date()
    except (ValueError, TypeError):
        pass

    try:
        return pd.to_datetime(val, format='%Y-%m-%d', errors='raise').date()
    except:
        pass

    try:
        return pd.to_datetime(val, dayfirst=True, errors='coerce').date()
    except:
        return pd.NaT

def update_csv_powerbi(df_new, chemin_csv):
    if df_new.empty: return "Aucune donnée."
    dossier = os.path.dirname(chemin_csv)
    if dossier and not os.path.exists(dossier): os.makedirs(dossier)

    try:
        try:
            df_hist = pd.read_csv(chemin_csv, sep=';', on_bad_lines='skip', encoding='utf-8-sig', engine='python', dtype={'Num Ticket': str, 'Num Bon': str})
        except UnicodeDecodeError:
            df_hist = pd.read_csv(chemin_csv, sep=';', on_bad_lines='skip', encoding='latin-1', engine='python', dtype={'Num Ticket': str, 'Num Bon': str})
    except (FileNotFoundError, pd.errors.EmptyDataError):
        df_hist = pd.DataFrame()
    
    if not df_hist.empty:
        df_hist = df_hist.loc[:, ~df_hist.columns.str.contains('^Unnamed')]

    for df in [df_hist, df_new]:
        for col in ["Num Ticket", "Num Bon"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    df_total = pd.concat([df_hist, df_new], ignore_index=True)
    
    if "Matiere_T" in df_total.columns and "Num Ticket" in df_total.columns:
        masque_total_invalide = (df_total["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)) & (df_total["Num Ticket"] == "")
        df_total = df_total[~masque_total_invalide]
    
    colonnes_a_verifier = [c for c in ["Num Ticket", "Num Bon", "Date_Ref", "Client", "Matiere_T"] if c in df_total.columns]
    if colonnes_a_verifier:
        df_total = df_total.dropna(subset=colonnes_a_verifier, how='all')

    # Dédoublonnage : On ne dédoublonne plus strictement sur le Numéro de Ticket
    # pour éviter d'écraser les doublons légitimes (ex: plusieurs pesées sous le même ticket ou homonymies).
    # On évite juste les doublons parfaits (lignes 100% identiques)
    df_total = df_total.drop_duplicates()
    
    if "Date_Ref" in df_total.columns:
        df_total["Date_Ref"] = df_total["Date_Ref"].apply(convertir_date_robuste)
        df_total["Date_Ref"] = pd.to_datetime(df_total["Date_Ref"], errors='coerce').dt.strftime('%Y-%m-%d').fillna("")

    for col in ["Num Ticket", "Num Bon"]:
        if col in df_total.columns:
            df_total[col] = df_total[col].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
            
    for col in ["Poids_Terrain", "Poids_Facture", "Ecart"]:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col], errors='coerce').astype(float)
    
    try:
        df_total.to_csv(chemin_csv, index=False, sep=';', encoding='utf-8-sig')
        return f"Base Power BI (CSV) mise à jour : {len(df_total)} lignes."
    except PermissionError:
        raise PermissionError("Fermez le fichier CSV (Excel) avant de lancer !")

# =============================================================================
# 2. LOGIQUE PICHETA
# =============================================================================

# Fonction pour préparer le DF final (Format immat.py)
def prepare_final(df_res):
    # Création colonnes normalisées si absentes
    if 'N° Document' not in df_res.columns: df_res['N° Document'] = np.nan

    # Reconstruction de la structure de sortie souhaitée
    result = pd.DataFrame()
    
    # Gestion des suffixes possibles pour Date_Clean
    if 'Date' in df_res.columns: result['Date'] = df_res['Date']
    elif 'Date_Match' in df_res.columns: result['Date'] = df_res['Date_Match']
    elif 'Date_Ref' in df_res.columns: 
        result['Date'] = df_res['Date_Ref'].apply(convertir_date_robuste)
    else: result['Date'] = np.nan

    # Poids Eco (Terrain)
    if 'Poids_Terrain' in df_res.columns: result['Poids_Eco'] = df_res['Poids_Terrain']
    elif 'Poids_Match' in df_res.columns: result['Poids_Eco'] = df_res['Poids_Match']
    else: result['Poids_Eco'] = np.nan

    # Plaque Eco (Terrain)
    if 'Immatriculation_T' in df_res.columns: result['Immat_Eco'] = df_res['Immatriculation_T']
    elif 'Immatriculation' in df_res.columns: result['Immat_Eco'] = df_res['Immatriculation']
    else: result['Immat_Eco'] = np.nan
    
    # Plaque Exutoire
    if 'Immatriculation_F' in df_res.columns: result['Immat_Exu'] = df_res['Immatriculation_F']
    else: result['Immat_Exu'] = result['Immat_Eco'] 

    # Ticket Eco
    if 'Num Ticket_T' in df_res.columns: result['Ticket_Eco'] = df_res['Num Ticket_T']
    elif 'Num Ticket' in df_res.columns: result['Ticket_Eco'] = df_res['Num Ticket']
    else: result['Ticket_Eco'] = np.nan
    
    # Ticket Exu (N° Document)
    # Dans app_picheta, on a Num Ticket pour les deux.
    # Si matché, Num Ticket est bon. 
    # Si right_only, Num Ticket contient la valeur exutoire.
    result['Ticket_Exu'] = df_res['Num Ticket']

    if 'Statut_Final' in df_res.columns: result['Statut'] = df_res['Statut_Final']
    else: result['Statut'] = np.where(df_res['_merge']=='both', 'OK', 'Non Trouvé')
    
    if 'Methode_Match' in df_res.columns: result['Methode'] = df_res['Methode_Match']
    else: result['Methode'] = 'N/A'
    
    # Poids Exu
    if 'Poids_Facture' in df_res.columns: result['Poids_Exu'] = df_res['Poids_Facture']
    else: result['Poids_Exu'] = np.nan

    # --- Comparaison Chantier ---
    result['NChantier_Eco'] = df_res.get('INT Client', '')
    result['Code_Adresse_Exu'] = df_res.get('EXT Client', '')
    
    s1 = result['NChantier_Eco'].astype(str).str.strip().str.upper().replace({'NAN': '', 'NONE': ''})
    s1 = s1.str.replace('MLV', '', regex=False).str.replace('MLJ', '', regex=False).str.strip()
    s2 = result['Code_Adresse_Exu'].astype(str).str.strip().str.upper().replace({'NAN': '', 'NONE': ''})
    
    result['Chantier_OK'] = np.where((s1 == s2) & (s1 != ''), 'OK', 'Diff')
    result.loc[(s1 == '') | (s2 == ''), 'Chantier_OK'] = 'Inconnu/Wait'
    result['Verif_Tonnes'] = (abs(result['Poids_Eco'] - result['Poids_Exu']) < 0.005).replace({True:'OK', False:'Pb.T'})

    return result

def charger_picheta(chemin, source):
    try:
        temp = pd.read_excel(chemin, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            row_str = str(r.values).lower()
            if "tp manuel" in row_str or "nature" in row_str: 
                idx = i; break
        
        print(f"Chargement {source}: Header trouvé ligne {idx}")
        df = pd.read_excel(chemin, header=idx)
        print(f"Chargement {source}: {len(df)} lignes brutes")

        cols = {}
        # Mapping plus strict pour éviter les collisions de colonnes (ex: Date vs Date Saisie)
        col_date_found = False
        
        for c in df.columns:
            cl = str(c).lower().strip()
            
            if "tp manuel" in cl: cols[c] = "Num Ticket"
            if cl in ["quantiteligne", "tonnages"]: cols[c] = "Poids_Terrain"
            if "nature" in cl or "description" in cl: cols[c] = "Matiere_T"
            
            # Priorité Date
            if cl == "date": 
                cols[c] = "Date_Ref"
                col_date_found = True
            elif "date" in cl and not col_date_found and "saisie" not in cl:
                # On prend une colonne 'date...' seulement si on n'a pas trouvé 'DATE' exact
                # et on évite 'date saisie' qui est souvent vide
                cols[c] = "Date_Ref"

            if "nchantier" in cl: cols[c] = "Client" 
            elif "exutoire" in cl and "Client" not in cols.values(): cols[c] = "Client" 
            
            if ("bon" in cl or "vidage" in cl) and "nbr" not in cl and "nombre" not in cl: cols[c] = "Num Bon"
            if "chauffeur" in cl: cols[c] = "Chauffeur"
            if "camion" in cl or "immatriculation" in cl: cols[c] = "Immatriculation"
        
        df = df.rename(columns=cols)
        df = df.loc[:, ~df.columns.duplicated()]

        if "Client" not in df.columns:
            df["Client"] = f"PICHETA {source}"

        if "Date_Ref" in df.columns:
            df["Date_Ref"] = df["Date_Ref"].apply(convertir_date_robuste)

        if "Poids_Terrain" in df.columns: 
            df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
            
        if "Num Ticket" in df.columns:
            df["Num Ticket"] = df["Num Ticket"].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        if "Num Bon" in df.columns:
            df["Num Bon"] = df["Num Bon"].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
        cols_obligatoires = [c for c in ["Num Ticket", "Poids_Terrain", "Date_Ref", "Immatriculation"] if c in df.columns]
        if cols_obligatoires:
             df = df.dropna(subset=cols_obligatoires, how='all')

        df["Activité"] = source
        return df
    except Exception as e: 
        print(f"Erreur chargement {source}: {e}")
        return pd.DataFrame()

def lancer_analyse():
    f_ctc = ent_ctc.get(); f_dech = ent_dech.get(); f_exp = ent_exp.get()
    
    if not f_exp: messagebox.showerror("Erreur", "Fichier Export manquant"); return

    bouton_lancer.config(text="Traitement...", state="disabled")
    root.update()

    try:
        dfs = []
        if f_ctc: dfs.append(charger_picheta(f_ctc, "CTC"))
        if f_dech: dfs.append(charger_picheta(f_dech, "DECH"))
        
        if not dfs: raise ValueError("Aucun fichier terrain valide.")
        df_ter = pd.concat(dfs, ignore_index=True)
        print(f"Total Terrain brut: {len(df_ter)} lignes")

        try: 
            df_ref = pd.read_excel(f_exp, header=0) 
        except: 
            df_ref = pd.read_excel(f_exp, header=8) 
        
        cols_ref = {}
        for c in df_ref.columns:
            cl = str(c).lower()
            if "document" in cl or "n° bon" in cl: cols_ref[c] = "Num Ticket"
            if "q liv" in cl or "poids" in cl: cols_ref[c] = "Poids_Facture"
            if "code adresse" in cl: cols_ref[c] = "TEMP_CodeAdresse"
            if "date" in cl: cols_ref[c] = "Date_Ref"
            if "immat" in cl or "véhicule" in cl: cols_ref[c] = "Immatriculation"

        df_ref = df_ref.rename(columns=cols_ref)
        df_ref = df_ref.loc[:, ~df_ref.columns.duplicated()]

        # FORCER EXT_Matiere
        df_ref['EXT_Matiere'] = "GRAVATS"

        # --- PREPARATION DES DONNEES POUR MATCHING AVANCE ---
        
        # 1. Nettoyage Ticket
        for df in [df_ter, df_ref]:
            if 'Num Ticket' in df.columns:
                df['Num Ticket'] = df['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace({'nan': '', 'NAN': '', 'None': ''})
            else:
                df['Num Ticket'] = ""
        
        # 2. Nettoyage Date (Format YYYY-MM-DD strict pour matching)
        for df in [df_ter, df_ref]:
            if 'Date_Ref' in df.columns:
                df['Date_Match'] = df['Date_Ref'].apply(convertir_date_robuste).astype(str)
            else:
                df['Date_Match'] = ""

        # 3. Nettoyage Plaque
        if 'Immatriculation' not in df_ter.columns: df_ter['Immatriculation'] = ""
        if 'Immatriculation' not in df_ref.columns: df_ref['Immatriculation'] = ""
        df_ter['Immat_Match'] = df_ter['Immatriculation'].apply(clean_plate)
        df_ref['Immat_Match'] = df_ref['Immatriculation'].apply(clean_plate)

        # 4. Nettoyage Poids (Arrondi 2 décimales pour matching)
        if 'Poids_Terrain' not in df_ter.columns: df_ter['Poids_Terrain'] = 0
        if 'Poids_Facture' not in df_ref.columns: df_ref['Poids_Facture'] = 0
        df_ter['Poids_Match'] = pd.to_numeric(df_ter['Poids_Terrain'], errors='coerce').fillna(0).round(2)
        df_ref['Poids_Match'] = pd.to_numeric(df_ref['Poids_Facture'], errors='coerce').fillna(0).round(2)

        if 'Matiere_T' in df_ter.columns:
            df_ter['Matiere_T'] = df_ter['Matiere_T'].apply(normaliser_matiere)
            
        if 'EXT_Matiere' in df_ref.columns:
            df_ref['EXT_Matiere_Norm'] = df_ref['EXT_Matiere'].apply(normaliser_matiere)
        else:
            df_ref['EXT_Matiere_Norm'] = ""

        # --- STRATEGIE EN 3 PHASES ---
        
        # Sauvegarde des colonnes originales
        cols_ter_orig = df_ter.columns.tolist()
        cols_ref_orig = df_ref.columns.tolist()
        
        # Définition de restore_columns (doit être définie avant utilisation dans la fonction imbriquée ou hors)
        def restore_columns(df, suffix, original_cols):
            cols = {}
            # 1. Récupérer les colonnes suffixées (conflit)
            for c in df.columns:
                if c.endswith(suffix):
                    base_name = c[:-len(suffix)]
                    cols[c] = base_name
            
            # 2. Récupérer les colonnes sans suffixe qui faisaient partie du DF original
            for c in original_cols:
                if c in df.columns and c not in cols.values():
                    cols[c] = c
            
            return df[list(cols.keys())].rename(columns=cols)

        # Helper pour filtrer les matches sur le client
        def filter_and_split_rejects(merged_df, original_cols_ter, original_cols_ref):
            # On suppose que merged_df contient UNIQUEMENT les matches ('both')
            if merged_df.empty:
                return merged_df, pd.DataFrame(), pd.DataFrame()

            # Identification des noms de colonnes Client
            # Dans charger_picheta: cols[c] = "Client"
            # Dans df_ref setup: cols_ref[c] = "TEMP_CodeAdresse"
            
            # Gestion des suffixes potentiels mis par pd.merge s'il y avait conflit (peu probable ici mais robuste)
            c_int = 'Client_T' if 'Client_T' in merged_df.columns else 'Client'
            c_ext = 'TEMP_CodeAdresse_F' if 'TEMP_CodeAdresse_F' in merged_df.columns else 'TEMP_CodeAdresse'

            # Application du filtre
            mask_ok = merged_df.apply(lambda r: check_client_compatibility(r, c_int, c_ext), axis=1)
            
            valid = merged_df[mask_ok].copy()
            rejected = merged_df[~mask_ok].copy()
            
            if rejected.empty:
                return valid, pd.DataFrame(), pd.DataFrame()
            
            # Reconstruction des lignes rejetées en format source pour réinjection
            # restore_columns a besoin de savoir si c'est _T ou _F
            # rejected est 'both', donc il a tout.
            
            rej_ter = restore_columns(rejected, '_T', original_cols_ter)
            rej_ref = restore_columns(rejected, '_F', original_cols_ref)
            
            return valid, rej_ter, rej_ref

        print("PHASE 1 : MATCHING TICKET")
        
        df_ter['Key_Ticket'] = df_ter['Num Ticket'].replace('', np.nan)
        df_ref['Key_Ticket'] = df_ref['Num Ticket'].replace('', np.nan)

        merged_p1 = pd.merge(df_ter, df_ref, left_on='Key_Ticket', right_on='Key_Ticket', how='outer', indicator=True, suffixes=('_T', '_F'))
        
        # Séparation initiale
        candidates_p1 = merged_p1[merged_p1['_merge'] == 'both'].copy()
        
        # Filtrage Client
        matched_p1, rej_ter_p1, rej_ref_p1 = filter_and_split_rejects(candidates_p1, cols_ter_orig, cols_ref_orig)
        matched_p1['Methode_Match'] = 'Ticket'
        
        if not rej_ter_p1.empty:
            print(f"  -> {len(rej_ter_p1)} matches rejetés pour incohérence Client (Dechetterie).")

        # Reste classique + Rejets
        resid_ter_p1 = merged_p1[merged_p1['_merge'] == 'left_only'].copy()
        resid_ref_p1 = merged_p1[merged_p1['_merge'] == 'right_only'].copy()
        
        df_ter_p2 = restore_columns(resid_ter_p1, '_T', cols_ter_orig)
        df_ref_p2 = restore_columns(resid_ref_p1, '_F', cols_ref_orig)
        
        # Réinjection des rejetés
        df_ter_p2 = pd.concat([df_ter_p2, rej_ter_p1], ignore_index=True)
        df_ref_p2 = pd.concat([df_ref_p2, rej_ref_p1], ignore_index=True)

        print(f"P1 Match: {len(matched_p1)} | Reste Terrain: {len(df_ter_p2)} | Reste Facture: {len(df_ref_p2)}")

        # PHASE 2 : MATCHING DATE + PLAQUE
        print("PHASE 2 : MATCHING DATE + PLAQUE")
        
        df_ter_p2['Key_Date'] = df_ter_p2['Date_Match'].replace('', np.nan)
        df_ter_p2['Key_Immat'] = df_ter_p2['Immat_Match'].replace('', np.nan)
        
        df_ref_p2['Key_Date'] = df_ref_p2['Date_Match'].replace('', np.nan)
        df_ref_p2['Key_Immat'] = df_ref_p2['Immat_Match'].replace('', np.nan)
        
        merged_p2 = pd.merge(
            df_ter_p2.dropna(subset=['Key_Date', 'Key_Immat']), 
            df_ref_p2.dropna(subset=['Key_Date', 'Key_Immat']), 
            on=['Key_Date', 'Key_Immat'], 
            how='outer', indicator=True, suffixes=('_T', '_F')
        )
        
        candidates_p2 = merged_p2[merged_p2['_merge'] == 'both'].copy()
        
        # Filtrage Client
        matched_p2, rej_ter_p2, rej_ref_p2 = filter_and_split_rejects(candidates_p2, cols_ter_orig, cols_ref_orig)
        matched_p2['Methode_Match'] = 'Date+Immat'

        resid_ter_p2_match = merged_p2[merged_p2['_merge'] == 'left_only'].copy()
        resid_ref_p2_match = merged_p2[merged_p2['_merge'] == 'right_only'].copy()
        
        df_ter_p3_candidates = restore_columns(resid_ter_p2_match, '_T', cols_ter_orig)
        df_ref_p3_candidates = restore_columns(resid_ref_p2_match, '_F', cols_ref_orig)
        
        # Réinjection des rejetés
        df_ter_p3_candidates = pd.concat([df_ter_p3_candidates, rej_ter_p2], ignore_index=True)
        df_ref_p3_candidates = pd.concat([df_ref_p3_candidates, rej_ref_p2], ignore_index=True)

        excluded_ter_p2 = df_ter_p2[df_ter_p2['Key_Date'].isna() | df_ter_p2['Key_Immat'].isna()]
        excluded_ref_p2 = df_ref_p2[df_ref_p2['Key_Date'].isna() | df_ref_p2['Key_Immat'].isna()]
        
        df_ter_p3 = pd.concat([df_ter_p3_candidates, excluded_ter_p2])
        df_ref_p3 = pd.concat([df_ref_p3_candidates, excluded_ref_p2])

        print(f"P2 Match: {len(matched_p2)} | Reste Terrain: {len(df_ter_p3)} | Reste Facture: {len(df_ref_p3)}")

        # PHASE 3 : MATCHING DATE + POIDS (Rescue)
        print("PHASE 3 : MATCHING DATE + POIDS")
        
        df_ter_p3['Key_Weight'] = df_ter_p3['Poids_Match'].replace(0, np.nan)
        df_ref_p3['Key_Weight'] = df_ref_p3['Poids_Match'].replace(0, np.nan)
        
        merged_p3 = pd.merge(
            df_ter_p3.dropna(subset=['Key_Date', 'Key_Weight']), 
            df_ref_p3.dropna(subset=['Key_Date', 'Key_Weight']), 
            on=['Key_Date', 'Key_Weight'], 
            how='outer', indicator=True, suffixes=('_T', '_F')
        )
        
        candidates_p3 = merged_p3[merged_p3['_merge'] == 'both'].copy()
        
        # Filtrage Client
        matched_p3, rej_ter_p3, rej_ref_p3 = filter_and_split_rejects(candidates_p3, cols_ter_orig, cols_ref_orig)
        matched_p3['Methode_Match'] = 'Date+Poids'
        
        resid_ter_final = merged_p3[merged_p3['_merge'] == 'left_only'].copy()
        resid_ref_final = merged_p3[merged_p3['_merge'] == 'right_only'].copy()
        
        unmatched_final_ter = restore_columns(resid_ter_final, '_T', cols_ter_orig)
        unmatched_final_ref = restore_columns(resid_ref_final, '_F', cols_ref_orig)
        
        # Réinjection des rejetés dans les unmatched finaux
        unmatched_final_ter = pd.concat([unmatched_final_ter, rej_ter_p3], ignore_index=True)
        unmatched_final_ref = pd.concat([unmatched_final_ref, rej_ref_p3], ignore_index=True)
        
        excluded_ter_p3 = df_ter_p3[df_ter_p3['Key_Date'].isna() | df_ter_p3['Key_Weight'].isna()]
        excluded_ref_p3 = df_ref_p3[df_ref_p3['Key_Date'].isna() | df_ref_p3['Key_Weight'].isna()]
        
        unmatched_final_ter = pd.concat([unmatched_final_ter, excluded_ter_p3])
        unmatched_final_ref = pd.concat([unmatched_final_ref, excluded_ref_p3])
        
        # --- CONSOLIDATION FINALE ---
        unmatched_final_ter['_merge'] = 'left_only'
        unmatched_final_ter['Methode_Match'] = 'Aucun'
        
        unmatched_final_ref['_merge'] = 'right_only'
        unmatched_final_ref['Methode_Match'] = 'Aucun'
        
        all_dfs = [matched_p1, matched_p2, matched_p3, unmatched_final_ter, unmatched_final_ref]
        merged = pd.concat(all_dfs, ignore_index=True)
        
        def coalesce(df, col_base, col1, col2):
            # On part de la colonne de base si elle existe, sinon vide
            if col_base in df.columns:
                base = df[col_base]
            else:
                base = pd.Series(np.nan, index=df.index)

            # On comble les trous avec la version Terrain (col1)
            if col1 in df.columns:
                base = base.fillna(df[col1])
            
            # On comble le reste avec la version Facture (col2)
            if col2 in df.columns:
                base = base.fillna(df[col2])
            
            df[col_base] = base
            return df
            
        merged = coalesce(merged, 'Num Ticket', 'Num Ticket_T', 'Num Ticket_F')
        merged = coalesce(merged, 'Date_Ref', 'Date_Ref_T', 'Date_Ref_F')
        merged = coalesce(merged, 'Immatriculation', 'Immatriculation_T', 'Immatriculation_F')
        merged['Chauffeur'] = merged.get('Chauffeur_T', merged.get('Chauffeur', ''))
        
        if "Date_Ref" in merged.columns:
            merged["Date_Ref"] = merged["Date_Ref"].apply(convertir_date_robuste)
            merged["Date_Ref"] = pd.to_datetime(merged["Date_Ref"], errors='coerce').dt.strftime('%Y-%m-%d').fillna("")

        if var_activer_filtre.get():
            d_deb = pd.to_datetime(cal_debut.get_date())
            d_fin = pd.to_datetime(cal_fin.get_date())
            merged['DT_Ref'] = pd.to_datetime(merged['Date_Ref'], errors='coerce')
            merged = merged[(merged['DT_Ref'] >= d_deb) & (merged['DT_Ref'] <= d_fin)]

        merged['Exutoire'] = "PICHETA"
        merged['Poids_Terrain'] = np.floor(pd.to_numeric(merged['Poids_Terrain'], errors='coerce').fillna(0) * 100) / 100
        merged['Poids_Facture'] = np.floor(pd.to_numeric(merged['Poids_Facture'], errors='coerce').fillna(0) * 100) / 100
        merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
        
        # Correction pour INT Client et EXT Client : on priorise la version matchée (_T/_F) 
        # mais on fallback sur la version brute (Target/Facture) si elle existe (pour les nons matchés)
        
        # INT CLIENT
        if 'Client_T' in merged.columns:
            merged['INT Client'] = merged['Client_T'].fillna(merged.get('Client', ''))
        else:
            merged['INT Client'] = merged.get('Client', '')
        merged['INT Client'] = merged['INT Client'].replace('', 'PICHETA INCONNU')

        # EXT CLIENT
        if 'TEMP_CodeAdresse_F' in merged.columns:
             merged['EXT Client'] = merged['TEMP_CodeAdresse_F'].fillna(merged.get('TEMP_CodeAdresse', ''))
        else:
             merged['EXT Client'] = merged.get('TEMP_CodeAdresse', '')

        remplacements = {
            "DECHETTERIE MLV VAUCOULEURS": "DECHETTERIE VAUCOULEURS", 
            "DECHETTERIE MLJ LES CLOSEAUX": "DECHETTERIE CLOSEAUX 2"
        }
        merged['INT Client'] = merged['INT Client'].replace(remplacements)
        
        merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
        
        m_t = merged.get('Matiere_T', merged.get('Matiere_T_T', ''))
        m_f = merged.get('EXT_Matiere_Norm', merged.get('EXT_Matiere_Norm_F', ''))
        merged['Matiere_T'] = m_t
        merged['EXT_Matiere'] = m_f
        
        merged['Verif_Matiere'] = 'OK'

        merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})

        def verifier_client(row):
            def clean_client_name(name):
                # On réutilise la fonction globale unifiée
                return clean_client_match(name)

            c_int = clean_client_name(row.get('INT Client', ''))
            c_ext = clean_client_name(row.get('EXT Client', ''))
            
            if not c_int or not c_ext: return "Inconnu"

            # Check égalité directe sur le nom normalisé (ex: CLOSEAUX == CLOSEAUX)
            if c_int == c_ext:
                return "OK"
            
            # Fallback inclusion
            if c_int in c_ext or c_ext in c_int:
                return "OK"
            
            return "Pb.Clt"

        merged['Verif_Client'] = merged.apply(verifier_client, axis=1)

        cols = ['Date_Ref', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket','Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 
                'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
        
        for c in cols: 
            if c not in merged.columns: merged[c] = ""
        
        print(f"--- TOTAL FINAL avant CSV: {len(merged)} lignes ---")
        msg = update_csv_powerbi(merged[cols], FICHIER_SORTIE)
        
        # --- EXPORT FICHIER DETAIL TYPE IMMAT.PY ---
        final_excel_df = prepare_final(merged)
        excel_output = "resultat_comparaison_picheta_app.xlsx"
        try:
            with pd.ExcelWriter(excel_output) as writer:
                final_excel_df.to_excel(writer, sheet_name='Resultats_Complets', index=False)
            messagebox.showinfo("Succès", f"Terminé !\nMatches Ticket: {len(matched_p1)}\nMatches Plaque: {len(matched_p2)}\nMatches Poids: {len(matched_p3)}\n\nFichier Excel généré : {excel_output}\n{msg}")
        except PermissionError:
             messagebox.showwarning("Fichier Excel Verrouillé", f"Impossible d'écrire {excel_output} (ouvert ?).\nLe CSV PowerBI a quand même été mis à jour.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        messagebox.showerror("Erreur", f"Une erreur est survenue : {str(e)}")
    finally:
        bouton_lancer.config(text="LANCER L'ANALYSE", state="normal")

# --- DESIGN ---
root = tk.Tk(); root.title("PICHETA"); root.geometry("600x650"); root.configure(bg="#f0f2f5")

def browse(e): 
    f = filedialog.askopenfilename()
    if f: e.delete(0,tk.END); e.insert(0,f)

def ajout_champ(txt):
    f=tk.Frame(root,bg="#f0f2f5"); f.pack(pady=5,fill="x",padx=20)
    tk.Label(f,text=txt,width=20,anchor="w",bg="#f0f2f5",font=("bold",10)).pack(side="left")
    e=tk.Entry(f,bd=2,relief="flat"); e.pack(side="left",fill="x",expand=True,padx=5,ipady=3)
    tk.Button(f,text="...",command=lambda:browse(e),bg="#ecf0f1").pack(side="left")
    return e

tk.Frame(root,bg="#2c3e50",height=50).pack(fill="x")
tk.Label(root,text="INTERFACE PICHETA",font=("Arial",16,"bold"),bg="#2c3e50",fg="white").place(x=200,y=10)

tk.Label(root,text="Fichiers Terrain",bg="#f0f2f5",font=("bold",11),fg="#2c3e50").pack(pady=(20,10))
ent_ctc=ajout_champ("Fichier CTC Gravats")
ent_dech=ajout_champ("Fichier DECH Gravats")

tk.Label(root,text="Facturation",bg="#f0f2f5",font=("bold",11),fg="#2c3e50").pack(pady=(20,10))
ent_exp=ajout_champ("Export Facturation Gravats")

f_d=tk.Frame(root,bg="#ecf0f1",bd=1,relief="solid"); f_d.pack(pady=20,padx=20,fill="x")
var_activer_filtre=tk.BooleanVar(value=False)
def toggle():
    s = "normal" if var_activer_filtre.get() else "disabled"
    cal_debut.config(state=s); cal_fin.config(state=s)

tk.Checkbutton(f_d,text="Filtrer par Date",variable=var_activer_filtre,command=toggle,bg="#ecf0f1").pack(pady=5)
cal_debut=DateEntry(f_d,width=12); cal_debut.pack(side="left",padx=20,pady=10); cal_debut.config(state="disabled")
cal_fin=DateEntry(f_d,width=12); cal_fin.pack(side="right",padx=20,pady=10); cal_fin.config(state="disabled")

bouton_lancer=tk.Button(root,text="LANCER L'ANALYSE",command=lancer_analyse,bg="#27ae60",fg="white",font=("bold",12),height=2)
bouton_lancer.pack(pady=20,fill="x",padx=40)

root.mainloop()