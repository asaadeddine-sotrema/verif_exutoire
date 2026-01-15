import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os
import unicodedata
import warnings
from tkcalendar import DateEntry 


warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
# FICHIER_SORTIE = r"A:\Amine Saad Eddine\verif_tonnage_valene\test.db"
FICHIER_SORTIE = 'A:\aminesaadeddine\verif_tonnage_valene\test.csv'
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
        return f"Base de données Power BI mise à jour : {len(df_total)} lignes."
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
            
        df["Num Ticket"] = pd.to_numeric(df["Num Ticket"], errors='coerce')
        
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
        df_ref['Num Ticket'] = pd.to_numeric(df_ref['Num Ticket'], errors='coerce')

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
            merged['DT_Ref'] = pd.to_datetime(merged['Date_Ref'].fillna(method='bfill'), dayfirst=True, errors='coerce')
            merged = merged[(merged['DT_Ref'] >= d_deb) & (merged['DT_Ref'] <= d_fin)]

        merged['Exutoire'] = "VALENE"
        merged['Poids_Terrain'] = merged['Poids_Terrain'].fillna(0)
        merged['Poids_Facture'] = merged['Poids_Facture'].fillna(0)
        merged['Ecart'] = merged['Poids_Terrain'] - merged['Poids_Facture']
        
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
        merged['Date_Ref'] = merged['Date_Ref'].fillna(method='bfill')
        merged['Date_Ref'] = pd.to_datetime(merged['Date_Ref'], dayfirst=True, errors='coerce').dt.date

        merged['Verif_Tonnes'] = (abs(merged['Ecart']) < 0.005).replace({True:'OK', False:'Pb.T'})
        merged['Verif_Matiere'] = (merged['Matiere_T'] == merged['EXT_Matiere_Norm']).replace({True:'OK', False:'Pb.Mat'})
        merged['Verif_Exutoire'] = (merged['_merge'] == 'both').replace({True:'OK', False:'Pb.Ext'})

        cols = ['Date_Ref', 'Exutoire', 'Client', 'Activité', 'Num Ticket','Num Bon', 'Chauffeur', 'Immatriculation', 'EXT_Matiere', 'Matiere_T', 
                'Verif_Tonnes', 'Verif_Matiere', 'Verif_Exutoire', 'Poids_Terrain', 'Poids_Facture', 'Ecart']
        
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