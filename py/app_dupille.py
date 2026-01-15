import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os
import unicodedata
import warnings
from tkcalendar import DateEntry 

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
FICHIER_SORTIE = 'A:\aminesaadeddine\verif_tonnage_valene\test.csv'

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
    return val

def update_csv_powerbi(df_new, chemin_csv):
    if df_new.empty: return "Aucune donnée."
    dossier = os.path.dirname(chemin_csv)
    if dossier and not os.path.exists(dossier): os.makedirs(dossier)

    # --- LECTURE HISTORIQUE (CSV) ---
    # --- LECTURE HISTORIQUE (CSV) ---
    try:
        try:
            # Essai 1 : UTF-8 (standard moderne / Excel) - Moteur Python plus robuste
            df_hist = pd.read_csv(chemin_csv, sep=';', on_bad_lines='skip', encoding='utf-8-sig', engine='python')
        except UnicodeDecodeError:
            # Essai 2 : Latin-1 / CP1252 (Windows par défaut)
            df_hist = pd.read_csv(chemin_csv, sep=';', on_bad_lines='skip', encoding='latin-1', engine='python')
    except (FileNotFoundError, pd.errors.EmptyDataError):
        df_hist = pd.DataFrame()
    
    df_total = pd.concat([df_hist, df_new], ignore_index=True)
    
    # --- NETTOYAGE RETROACTIF (POUR L'HISTORIQUE) ---
    # On applique les filtres sur tout le fichier pour retirer les erreurs passées
    if "Matiere_T" in df_total.columns and "Num Ticket" in df_total.columns:
        # 1. On retire les lignes "Total" ou "Récap" qui n'ont pas de numéro de ticket
        masque_total_invalide = (df_total["Matiere_T"].astype(str).str.contains("total|récap", case=False, na=False)) & (df_total["Num Ticket"].isna())
        df_total = df_total[~masque_total_invalide]
    
    # 2. On retire les lignes complètement vides ou bugs (lignes fantômes)
    colonnes_a_verifier = [c for c in ["Num Ticket", "Num Bon", "Date_Ref", "Client", "Matiere_T"] if c in df_total.columns]
    if colonnes_a_verifier:
        df_total = df_total.dropna(subset=colonnes_a_verifier, how='all')

    df_total = df_total.drop_duplicates(subset=['Num Ticket', 'Exutoire'], keep='last')
    
    # --- ENFORCEMENT DES TYPES (STRICT) ---
    # 1. Date -> Format Date strict (YYYY-MM-DD)
    if "Date_Ref" in df_total.columns:
        df_total["Date_Ref"] = pd.to_datetime(df_total["Date_Ref"], dayfirst=True, errors='coerce').dt.date

    # 2. Numéros -> Entiers stricts (Int64 : pas de décimales, gère les vides)
    for col in ["Num Ticket", "Num Bon"]:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col], errors='coerce').round().astype("Int64")
            
    # 3. Poids -> Float strict
    for col in ["Poids_Terrain", "Poids_Facture", "Ecart"]:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col], errors='coerce').astype(float)
    
    try:
        # Sauvegarde en CSV avec séparateur point-virgule
        df_total.to_csv(chemin_csv, index=False, sep=';', encoding='utf-8-sig')
        return f"Base Power BI mise à jour : {len(df_total)} lignes."
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
        df_lb['Num Ticket'] = pd.to_numeric(df_lb['Num Ticket'], errors='coerce')
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
        df_fac['Num Ticket'] = pd.to_numeric(df_fac['Num Ticket'], errors='coerce')

        # 3. Merge
        df_lb['Matiere_T'] = df_lb['Matiere_T'].apply(normaliser_matiere)
        df_fac['EXT_Matiere_Norm'] = df_fac['EXT_Matiere'].apply(normaliser_matiere)
        
        merged = pd.merge(df_lb, df_fac, on='Num Ticket', suffixes=('_T', '_F'), how='outer', indicator=True)
        
        # Filtre Date
        if var_activer_filtre.get():
            d_deb = pd.to_datetime(cal_debut.get_date())
            d_fin = pd.to_datetime(cal_fin.get_date())
            merged['DT'] = pd.to_datetime(merged['Date_Ref_F'].fillna(merged['Date_Ref_T']), dayfirst=True, errors='coerce')
            merged = merged[(merged['DT'] >= d_deb) & (merged['DT'] <= d_fin)]

        # Calculs
        merged['Exutoire'] = "DUPILLE"
        merged['Poids_Terrain'] = merged['Poids_Terrain'].fillna(0)
        merged['Poids_Facture'] = merged['Poids_Facture'].fillna(0)
        merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
        
        merged['Date_Ref'] = merged['Date_Ref_F'].fillna(merged['Date_Ref_T'])
        merged['Date_Ref'] = pd.to_datetime(merged['Date_Ref'], dayfirst=True, errors='coerce').dt.date
        merged['Client'] = merged['Client_F'].fillna(merged['Client_T'])
        merged['Activité'] = merged['Activité_F'].fillna("INCONNU")
        
        merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
        merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'})
        merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})

        # Export
        cols = ['Date_Ref', 'Exutoire', 'Client', 'Activité', 'Num Ticket','Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 
                'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
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