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

# --- UTILITAIRES ---
def nettoyer_texte(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def normaliser_matiere(valeur_origine):
    val = nettoyer_texte(valeur_origine)
    if "VERTS" in val: return "DECHETS VERTS"
    if "VEGETAUX" in val: return "DECHETS VERTS"
    if "BOIS" in val: return "BOIS"
    if any(x in val for x in ["DECHETS IND", "ORDURES MEN"]): return "ORDURES MENAGERES"
    if any(x in val for x in ["DECHETS IND", "ORDURES MEN"]): return "ORDURES MENAGERES"
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
        if val_num > 30000: # Excel base date usually 1899-12-30
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
                df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    df_total = pd.concat([df_hist, df_new], ignore_index=True)
    
    # --- NETTOYAGE RETROACTIF (HISTORIQUE) ---
    if "Matiere_T" in df_total.columns and "Num Ticket" in df_total.columns:
        masque_total_invalide = (df_total["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)) & (df_total["Num Ticket"] == "")
        df_total = df_total[~masque_total_invalide]
    
    colonnes_a_verifier = [c for c in ["Num Ticket", "Num Bon", "Date_Ref", "Client", "Matiere_T"] if c in df_total.columns]
    if colonnes_a_verifier:
        df_total = df_total.dropna(subset=colonnes_a_verifier, how='all')

    df_total = df_total.drop_duplicates(subset=['Num Ticket', 'Exutoire'], keep='last')
    
    # --- ENFORCEMENT DES TYPES (STRICT) ---
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
            
    # 3. Poids -> DECIMAL
    for col in ["Poids_Terrain", "Poids_Facture", "Ecart"]:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col], errors='coerce').astype(float)
    
    try:
        df_total.to_csv(chemin_csv, index=False, sep=';', encoding='utf-8-sig')
        return f"Base Power BI (CSV) mise à jour : {len(df_total)} lignes."
    except PermissionError:
        raise PermissionError("Fermez le fichier CSV !")

# --- LOGIQUE DUPILLE ---
def lancer_analyse():
    f_lb = ent_lb.get(); f_fac = ent_fac.get()
    if not f_lb or not f_fac: messagebox.showerror("Erreur", "Fichiers manquants"); return

    bouton_lancer.config(text="Traitement...", state="disabled")
    root.update()

    try:
        # 1. Terrain LB
        temp = pd.read_excel(f_lb, header=None, nrows=15)
        idx = 0
        for i, r in temp.iterrows(): 
            if "Num Ticket" in str(r.values): idx = i; break
        df_lb = pd.read_excel(f_lb, header=idx)
        cols = {'Description': 'Matiere_T', 'Poids en Tonnes': 'Poids_Terrain', 'Exutoire': 'Client', 'Date': 'Date_Ref'}
        for c in df_lb.columns:
            if "bon" in str(c).lower(): cols[c] = "Num Bon"
            if "chauffeur" in str(c).lower() or "conducteur" in str(c).lower(): cols[c] = "Chauffeur"
            if "immat" in str(c).lower() or "véhicule" in str(c).lower(): cols[c] = "Immatriculation"
        df_lb = df_lb.rename(columns=cols)
        # FORCE STRING
        df_lb['Num Ticket'] = df_lb['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        if 'Num Bon' in df_lb.columns:
             df_lb['Num Bon'] = df_lb['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
        df_lb['Activité'] = "LB_DUPILLE"

        # 2. Facture Multi-onglets
        xls = pd.ExcelFile(f_fac)
        frames = []
        for sheet in xls.sheet_names:
            if "pap" in str(sheet).lower():
                d = pd.read_excel(f_fac, sheet_name=sheet, header=None)
                if len(d.columns) > 7:
                    d = d.rename(columns={0: 'Num Ticket', 1: 'Date_Ref', 2: 'Client', 6: 'EXT_Matiere', 7: 'net'})
                    d['Activité'] = "PAP"
                    frames.append(d)
            else:
                d_head = pd.read_excel(f_fac, sheet_name=sheet, header=None, nrows=10)
                idx = 0
                for i, r in d_head.iterrows():
                    if "ID" in str(r.values): idx = i; break
                d = pd.read_excel(f_fac, sheet_name=sheet, header=idx)
                d = d.rename(columns={'ID': 'Num Ticket', 'lib_produit': 'EXT_Matiere', 'lib_client': 'Client', 'Dates': 'Date_Ref'})
                d['Activité'] = "DECHETTERIE"
                frames.append(d)
        
        df_fac = pd.concat(frames, ignore_index=True)
        if 'net' in df_fac.columns: df_fac['Poids_Facture'] = pd.to_numeric(df_fac['net'], errors='coerce') / 1000
        # FORCE STRING Facture
        df_fac['Num Ticket'] = df_fac['Num Ticket'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')

        # 3. Merge
        df_lb['Matiere_T'] = df_lb['Matiere_T'].apply(normaliser_matiere)
        df_fac['EXT_Matiere_Norm'] = df_fac['EXT_Matiere'].apply(normaliser_matiere)
        
        merged = pd.merge(df_lb, df_fac, on='Num Ticket', suffixes=('_T', '_F'), how='outer', indicator=True)
        
        # Filtre Date
        if var_activer_filtre.get():
            d_deb = pd.to_datetime(cal_debut.get_date())
            d_fin = pd.to_datetime(cal_fin.get_date())
            # Utilisation de la conversion robuste pour le filtre
            merged['DT'] = merged['Date_Ref_F'].fillna(merged['Date_Ref_T']).apply(convertir_date_robuste)
            # Conversion explicite en datetime pour la comparaison (car la fonction renvoie date ou timestamp)
            merged['DT'] = pd.to_datetime(merged['DT'], errors='coerce')
            merged = merged[(merged['DT'] >= d_deb) & (merged['DT'] <= d_fin)]

        # Calculs
        merged['Exutoire'] = "DUPILLE"
        merged['Poids_Terrain'] = np.floor(pd.to_numeric(merged['Poids_Terrain'], errors='coerce').fillna(0) * 100) / 100
        merged['Poids_Facture'] = np.floor(pd.to_numeric(merged['Poids_Facture'], errors='coerce').fillna(0) * 100) / 100
        merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
        
        merged['Date_Ref'] = merged['Date_Ref_F'].fillna(merged['Date_Ref_T'])
        merged['Date_Ref'] = merged['Date_Ref'].apply(convertir_date_robuste)
        merged['Client'] = merged['Client_F'].fillna(merged['Client_T'])
        merged['INT Client'] = merged.get('Client_T', '')
        merged['EXT Client'] = merged.get('Client_F', '')
        merged['Activité'] = merged['Activité_F'].fillna("INCONNU")
        
        merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
        merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'})
        merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})

        def verifier_client(row):
            c_int = str(row.get('INT Client', '')).strip().upper()
            c_ext = str(row.get('EXT Client', '')).strip().upper()
            
            # Rule: GPSO <-> DUPILLE SARL (CU GPSO)
            if "GPSO" in c_ext:
                 if "DUPILLE SARL (CU GPSO)" in c_int:
                     return "OK"
                 else:
                     return "Pb.Clt"

            if "DUPILLE SARL (CU GPSO)" in c_int:
                 if "GPSO" in c_ext:
                     return "OK"
                 else:
                     return "Pb.Clt"
            
            return "OK"

        merged['Verif_Client'] = merged.apply(verifier_client, axis=1)

        # Export
        cols = ['Date_Ref', 'Exutoire', 'Client', 'INT Client', 'EXT Client', 'Activité', 'Num Ticket','Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 
                'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Verif_Client', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
        for c in cols: 
            if c not in merged.columns: merged[c] = ""
        
        # Définition du chemin de sortie DB
        # Utilisation de la constante globale
        FICHIER_DB = FICHIER_SORTIE
        
        msg = update_csv_powerbi(merged[cols], FICHIER_DB)
        messagebox.showinfo("Succès", f"Terminé !\n{msg}")

    except Exception as e:
        messagebox.showerror("Erreur", str(e))
    finally:
        bouton_lancer.config(text="LANCER L'ANALYSE", state="normal")

if __name__ == "__main__":
    # --- GUI ---
    root = tk.Tk(); root.title("DUPILLE"); root.geometry("500x450"); root.configure(bg="#f0f2f5")

    def browse(e): 
        f = filedialog.askopenfilename()
        if f: e.delete(0,tk.END); e.insert(0,f)

    def ajout_champ(txt):
        f=tk.Frame(root,bg="#f0f2f5"); f.pack(pady=5,fill="x",padx=20)
        tk.Label(f,text=txt,width=15,anchor="w",bg="#f0f2f5").pack(side="left")
        e=tk.Entry(f); e.pack(side="left",fill="x",expand=True,padx=5)
        tk.Button(f,text="...",command=lambda:browse(e)).pack(side="left")
        return e

    tk.Label(root,text="INTERFACE DUPILLE",font=("bold",14),bg="#27ae60",fg="white",pady=10).pack(fill="x")
    tk.Label(root,text="Fichiers",bg="#f0f2f5",font=("bold",10)).pack(pady=10)
    ent_lb=ajout_champ("Terrain (LB)")
    ent_fac=ajout_champ("Facture")

    f_d=tk.Frame(root,bg="#ecf0f1",bd=1,relief="solid"); f_d.pack(pady=15,padx=20,fill="x")
    var_activer_filtre=tk.BooleanVar(value=False)
    tk.Checkbutton(f_d,text="Filtrer Date",variable=var_activer_filtre,bg="#ecf0f1").pack()
    cal_debut=DateEntry(f_d); cal_debut.pack(side="left",padx=10,pady=5)
    cal_fin=DateEntry(f_d); cal_fin.pack(side="right",padx=10,pady=5)

    bouton_lancer=tk.Button(root,text="LANCER L'ANALYSE",command=lancer_analyse,bg="#27ae60",fg="white",font=("bold",11),height=2)
    bouton_lancer.pack(pady=20,fill="x",padx=40)

    root.mainloop()