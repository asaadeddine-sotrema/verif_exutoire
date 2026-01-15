import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os
import numpy as np
import unicodedata
import warnings
from tkcalendar import DateEntry 
import sqlite3
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

def normaliser_matiere(valeur_origine):
    val = nettoyer_texte(valeur_origine)
    if any(x in val for x in ["DECHETS IND", "ORDURES MEN", "DIB", "O.M"]): return "ORDURES MENAGERES"
    if any(x in val for x in ["EMBALLAGES", "RECYCLABLES", "TRI SELECTIF"]): return "EMBALLAGES MENAGERS RECUPEREES"
    if "VERRE" in val: return "VERRE"
    if "CARTON" in val: return "CARTON"
    if "BOIS" in val: return "BOIS"
    return val

def convertir_date_robuste(val):
    """
    Convertit une valeur (texte, date ou nombre Excel) en date standard YYYY-MM-DD.
    Gère les entiers Excel (ex: 45962 -> 2025-11-...)
    """
    if pd.isna(val) or val == "":
        return pd.NaT
    
    # 1. Si c'est déjà un type date/datetime
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime.date):
        return val

    # 2. Si c'est un nombre (int/float/str numeric) -> Format Excel Serial Date
    try:
        val_num = float(val)
        if val_num > 30000:
            return pd.to_datetime(val_num, unit='D', origin='1899-12-30').date()
    except (ValueError, TypeError):
        pass

    # 3. Si c'est du texte classique
    try:
        # D'abord on tente le format strict ISO (YYYY-MM-DD) car dayfirst=True peut casser l'ISO
        return pd.to_datetime(val, format='%Y-%m-%d', errors='raise').date()
    except:
        pass

    try:
        # Ensuite on tente le format français (JJ/MM/AAAA)
        return pd.to_datetime(val, dayfirst=True, errors='coerce').date()
    except:
        return pd.NaT

def update_csv_powerbi(df_new, chemin_csv):
    if df_new.empty: return "Aucune donnée."
    dossier = os.path.dirname(chemin_csv)
    if dossier and not os.path.exists(dossier): os.makedirs(dossier)

    # --- LECTURE HISTORIQUE (CSV) ---
    try:
        try:
            # Essai 1 : UTF-8
            df_hist = pd.read_csv(chemin_csv, sep=';', on_bad_lines='skip', encoding='utf-8-sig', engine='python', dtype={'Num Ticket': str, 'Num Bon': str})
        except UnicodeDecodeError:
            # Essai 2 : Latin-1
            df_hist = pd.read_csv(chemin_csv, sep=';', on_bad_lines='skip', encoding='latin-1', engine='python', dtype={'Num Ticket': str, 'Num Bon': str})
    except (FileNotFoundError, pd.errors.EmptyDataError):
        df_hist = pd.DataFrame()
    
    # Nettoyage des colonnes parasites
    if not df_hist.empty:
        df_hist = df_hist.loc[:, ~df_hist.columns.str.contains('^Unnamed')]

    # Harmonisation des types avant concaténation (IDs en Token string)
    for df in [df_hist, df_new]:
        for col in ["Num Ticket", "Num Bon"]:
            if col in df.columns:
                # On nettoie les .0 éventuels pour avoir du texte propre
                df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    df_total = pd.concat([df_hist, df_new], ignore_index=True)
    
    # --- NETTOYAGE RETROACTIF ---
    if "Matiere_T" in df_total.columns and "Num Ticket" in df_total.columns:
        masque_total_invalide = (df_total["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)) & (df_total["Num Ticket"] == "")
        df_total = df_total[~masque_total_invalide]
    
    colonnes_a_verifier = [c for c in ["Num Ticket", "Num Bon", "Date_Ref", "Client", "Matiere_T"] if c in df_total.columns]
    if colonnes_a_verifier:
        df_total = df_total.dropna(subset=colonnes_a_verifier, how='all')

    # Dédoublonnage sur Num Ticket + Exutoire (on garde le plus récent = 'last')
    df_total = df_total.drop_duplicates(subset=['Num Ticket', 'Exutoire'], keep='last')
    
    # --- ENFORCEMENT DES TYPES (STRICT - Demande User) ---
    # 1. Date -> Format Date strict (JJ/MM/AAAA)
    if "Date_Ref" in df_total.columns:
        # D'abord on s'assure d'avoir des objets Date propres
        df_total["Date_Ref"] = df_total["Date_Ref"].apply(convertir_date_robuste)
        # Puis on force le format String ISO (AAAA-MM-JJ) pour éviter les erreurs d'interprétation Day/Month
        df_total["Date_Ref"] = pd.to_datetime(df_total["Date_Ref"], errors='coerce').dt.strftime('%Y-%m-%d').fillna("")

    # 2. Numéros -> TEXTE
    for col in ["Num Ticket", "Num Bon"]:
        if col in df_total.columns:
            df_total[col] = df_total[col].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
            
    # 3. Poids -> DECIMAL (float)
    for col in ["Poids_Terrain", "Poids_Facture", "Ecart"]:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col], errors='coerce').astype(float)
    
    try:
        df_total.to_csv(chemin_csv, index=False, sep=';', encoding='utf-8-sig')
        return f"Base Power BI (CSV) mise à jour : {len(df_total)} lignes."
    except PermissionError:
        raise PermissionError("Fermez le fichier CSV !")

# =============================================================================
# 2. LOGIQUE VALENE (CORRIGÉE)
# =============================================================================

def charger_valene(chemin, source):
    try:
        temp = pd.read_excel(chemin, header=None, nrows=20)
        idx = 0
        for i, r in temp.iterrows():
            if "Num Ticket" in str(r.values) or "N° de pesée" in str(r.values): idx = i; break
        
        df = pd.read_excel(chemin, header=idx)
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
        
        # --- CORRECTION CLIENT ---
        # Si pas de colonne Client trouvée, on en crée une par défaut
        if "Client" not in df.columns:
            df["Client"] = f"VALENE {source}"

        if "Poids_Terrain" in df.columns: df["Poids_Terrain"] = pd.to_numeric(df["Poids_Terrain"], errors='coerce')
        elif "Poids_KG" in df.columns: df["Poids_Terrain"] = pd.to_numeric(df["Poids_KG"], errors='coerce') / 1000
            
        # FORCE STRING pour Num Ticket (pour éviter la suppression des tickets alphanumériques)
        if "Num Ticket" in df.columns:
            df["Num Ticket"] = df["Num Ticket"].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        if "Num Bon" in df.columns:
            df["Num Bon"] = df["Num Bon"].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        
        # --- FILTRAGE INTELLIGENT ---
        # 1. On vire la ligne "Total" si identifiée (contient "Total" et pas de ticket)
        if "Matiere_T" in df.columns:
            mask_total = (df["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)) & (df["Num Ticket"].isna())
            df = df[~mask_total]
            
        # 2. On vire les lignes "presque vides" (qui n'ont ni Ticket, ni Bon, ni Date, ni Client, ni Matière)
        cols_ctx = [c for c in ["Num Ticket", "Num Bon", "Date_Ref", "Client", "Matiere_T"] if c in df.columns]
        if cols_ctx:
            df = df.dropna(subset=cols_ctx, how='all')

        df["Activité"] = source
        return df
    except: return pd.DataFrame()

def lancer_analyse():
    f_pap = ent_pap.get(); f_pav = ent_pav.get(); f_sot = ent_sot.get(); f_exp = ent_exp.get()
    
    if not f_exp: messagebox.showerror("Erreur", "Fichier Export manquant"); return

    bouton_lancer.config(text="Traitement...", state="disabled")
    root.update()

    try:
        dfs = []
        if f_pap: dfs.append(charger_valene(f_pap, "PAP"))
        if f_pav: dfs.append(charger_valene(f_pav, "PAV"))
        if f_sot: dfs.append(charger_valene(f_sot, "SOTREMA2"))
        
        if not dfs: raise ValueError("Aucun fichier terrain valide.")
        df_ter = pd.concat(dfs, ignore_index=True)

        try: df_ref = pd.read_excel(f_exp, sheet_name="RPT_RecherchePeseeDetaillee", header=8)
        except: df_ref = pd.read_excel(f_exp, header=8)
        
        df_ref = df_ref.rename(columns={'N° de pesée': 'Num Ticket', 'Poids de la matière': 'Poids_Facture', 'Matière réalisée': 'EXT_Matiere'})
        # FORCE STRING pour Num Ticket (côté Facture)
        df_ref['Num Ticket'] = df_ref['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

        df_ter['Matiere_T'] = df_ter['Matiere_T'].apply(normaliser_matiere)
        df_ref['EXT_Matiere_Norm'] = df_ref['EXT_Matiere'].apply(normaliser_matiere)
        
        merged = pd.merge(df_ter, df_ref, on='Num Ticket', how='outer', indicator=True, suffixes=('_T', '_F'))
        
        # --- RECONSTRUCTION COLONNES APRES MERGE ---
        # Si collision, on récupère la version Terrain (_T), sinon on garde l'originale
        def restaurer_col(df, nom_col):
            if nom_col in df.columns: return df[nom_col]
            col_t, col_f = f"{nom_col}_T", f"{nom_col}_F"
            if col_t in df.columns: return df[col_t].fillna(df.get(col_f, ""))
            if col_f in df.columns: return df[col_f]
            return pd.Series([None]*len(df))

        merged['Client'] = restaurer_col(merged, 'Client')
        merged['Date_Ref'] = restaurer_col(merged, 'Date_Ref')
        merged['Chauffeur'] = restaurer_col(merged, 'Chauffeur')
        merged['Immatriculation'] = restaurer_col(merged, 'Immatriculation')

        if var_activer_filtre.get():
            d_deb = pd.to_datetime(cal_debut.get_date())
            d_fin = pd.to_datetime(cal_fin.get_date())
            # On cherche la date (soit Terrain, soit Facture)
            merged['DT_Ref'] = merged['Date_Ref'].apply(convertir_date_robuste)
            merged['DT_Ref'] = pd.to_datetime(merged['DT_Ref'], errors='coerce')
            merged = merged[(merged['DT_Ref'] >= d_deb) & (merged['DT_Ref'] <= d_fin)]

        merged['Exutoire'] = "VALENE"
        merged['Poids_Terrain'] = np.floor(pd.to_numeric(merged['Poids_Terrain'], errors='coerce').fillna(0) * 100) / 100
        merged['Poids_Facture'] = np.floor(pd.to_numeric(merged['Poids_Facture'], errors='coerce').fillna(0) * 100) / 100
        merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
        
        merged['INT Client'] = merged.get('Client_T', merged.get('Client', ''))
        merged['EXT Client'] = merged.get('Client_F', '')

        # Sécurité Client
        if 'Client' not in merged.columns: merged['Client'] = "VALENE INCONNU"
        merged['Client'] = merged['Client'].fillna("VALENE")
        
        # --- REMPLACEMENT CLIENTS SPECIFIQUES ---
        remplacements = {
            "CU GPSO": "GPSO", 
            "CU GRAND PARIS SEINE ET OISE - AUBE": "GPSO"
        }
        merged['Client'] = merged['Client'].replace(remplacements)
        
        if 'Date_Ref' not in merged.columns: merged['Date_Ref'] = ""
        merged['Date_Ref'] = merged['Date_Ref'].apply(convertir_date_robuste)

        merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
        merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'})
        merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})

        def verifier_client(row):
            c_int = str(row.get('INT Client', '')).strip().upper()
            c_ext = str(row.get('EXT Client', '')).strip().upper()
            
            # Règle Spécifique GPSO / CCPIF
            if c_int in ["CU GPSO", "CCPIF"]:
                if "CU GRAND PARIS SEINE ET OISE - AUBE" in c_ext:
                    return "OK"
                else:
                    return "Pb.Clt"
            
            # Réciprocité
            if "CU GRAND PARIS SEINE ET OISE - AUBE" in c_ext:
                 if c_int in ["CU GPSO", "CCPIF"]:
                      return "OK"
                 else:
                      return "Pb.Clt"
            
            # Par défaut OK
            return "OK"

        merged['Verif_Client'] = merged.apply(verifier_client, axis=1)

        cols = ['Date_Ref', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket','Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 
                'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
        
        for c in cols: 
            if c not in merged.columns: merged[c] = ""
        
        msg = update_csv_powerbi(merged[cols], FICHIER_SORTIE)
        messagebox.showinfo("Succès", f"Terminé !\n{msg}")

    except Exception as e:
        messagebox.showerror("Erreur", f"Une erreur est survenue : {str(e)}")
    finally:
        bouton_lancer.config(text="LANCER L'ANALYSE", state="normal")

# --- DESIGN ---
root = tk.Tk(); root.title("VALENE"); root.geometry("600x650"); root.configure(bg="#f0f2f5")

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
tk.Label(root,text="INTERFACE VALENE",font=("Arial",16,"bold"),bg="#2c3e50",fg="white").place(x=200,y=10)

tk.Label(root,text="Fichiers Terrain",bg="#f0f2f5",font=("bold",11),fg="#2c3e50").pack(pady=(20,10))
ent_pap=ajout_champ("Fichier PAP")
ent_pav=ajout_champ("Fichier PAV")
ent_sot=ajout_champ("Fichier SOTREMA")

tk.Label(root,text="Facturation",bg="#f0f2f5",font=("bold",11),fg="#2c3e50").pack(pady=(20,10))
ent_exp=ajout_champ("Export Sotrema")

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