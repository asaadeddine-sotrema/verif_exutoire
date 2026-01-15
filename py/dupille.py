import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os
import glob
import unicodedata
from tkcalendar import DateEntry 
import sys

# --- FONCTIONS DE TRAITEMENT ---

def nettoyer_texte(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    txt = ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')
    return txt

def normaliser_matiere(valeur_origine):
    valeur_clean = nettoyer_texte(valeur_origine)
    
    # Dictionnaire adapté aux déchets verts et bois (spécifique Dupille)
    if "VERTS" in valeur_clean or "VEGETAUX" in valeur_clean: return "DECHETS VERTS"
    if "BOIS" in valeur_clean: return "BOIS"
    
    termes_om = ["DECHETS INDUSTRIELS", "ORDURES MENAGERES", "DIB", "O.M"]
    if any(x in valeur_clean for x in termes_om): return "ORDURES MENAGERES"
        
    termes_emb = ["EMBALLAGES MENAGERS", "RECYCLABLES", "TRI SELECTIF"]
    if any(x in valeur_clean for x in termes_emb): return "EMBALLAGES MENAGERS RECUPEREES"
        
    if "VERRE" in valeur_clean: return "VERRE"
    if "CARTON" in valeur_clean: return "CARTON"

    return valeur_clean

def auto_ajuster_colonnes(writer, df, sheet_name):
    worksheet = writer.sheets[sheet_name]
    for idx, col in enumerate(df.columns):
        max_len = len(str(col))
        try:
            if not df[col].empty:
                max_data = df[col].astype(str).map(len).max()
                if pd.notna(max_data): max_len = max(max_len, int(max_data))
        except: pass
        worksheet.set_column(idx, idx, min(max_len + 2, 60))

# --- MOTEUR D'ANALYSE DUPILLE ---

def lancer_analyse():
    f_terrain = entree_terrain.get()
    f_facture = entree_facture.get()

    if not f_terrain or not f_facture:
        messagebox.showwarning("Attention", "Veuillez sélectionner le fichier Terrain (LB) et le fichier Facture.")
        return

    bouton_lancer.config(text="Traitement en cours...", state="disabled")
    root.update()

    try:
        # === 1. CHARGEMENT TERRAIN (LB DUPILLE) ===
        # On cherche la ligne d'en-tête (souvent ligne 3 ou 4)
        df_scan = pd.read_excel(f_terrain, header=None, nrows=15)
        h_idx = 0
        for i, row in df_scan.iterrows():
            if "Num Ticket" in str(row.values):
                h_idx = i; break
        
        df_terrain = pd.read_excel(f_terrain, header=h_idx)
        
        # Nettoyage Terrain
        df_terrain = df_terrain.rename(columns={'Description': 'Matière'})
        # Sécurité : suppression doublons colonnes
        df_terrain = df_terrain.loc[:, ~df_terrain.columns.duplicated()]
        
        if 'Immatriculation' not in df_terrain.columns: df_terrain['Immatriculation'] = ''
        
        if 'Num Ticket' in df_terrain.columns:
            df_terrain['Num Ticket'] = pd.to_numeric(df_terrain['Num Ticket'], errors='coerce')
        if 'Poids en Tonnes' in df_terrain.columns:
            df_terrain['Poids en Tonnes'] = pd.to_numeric(df_terrain['Poids en Tonnes'], errors='coerce')
        
        # Identification Source Terrain (Pour le tri final)
        # On ne sait pas encore si c'est PAP ou Déchèterie juste avec le terrain,
        # On mettra "DUPILLE" par défaut, le croisement nous le dira via la facture.
        df_terrain['TypeTournee'] = "DUPILLE"

        # === 2. CHARGEMENT FACTURE (MULTI-ONGLETS) ===
        xls = pd.ExcelFile(f_facture)
        frames_facture = []

        for sheet in xls.sheet_names:
            sheet_nom = str(sheet).lower()
            
            # --- CAS A : Onglet PAP (Pas d'en-tête, commence ligne 1) ---
            if "pap" in sheet_nom:
                # Lecture sans header
                d_pap = pd.read_excel(f_facture, sheet_name=sheet, header=None)
                # Mapping manuel basé sur tes fichiers (Col 0=Ticket, Col 6=Matière, Col 7=Poids KG)
                # On vérifie qu'il y a assez de colonnes
                if len(d_pap.columns) >= 8:
                    d_pap = d_pap.rename(columns={0: 'Num Ticket', 1: 'Date', 6: 'Matière', 7: 'net'})
                    d_pap['Type_Flux'] = "PAP"
                    # Nom Client (souvent colonne 2 'GPSO')
                    if 2 in d_pap.columns: d_pap['Client'] = d_pap[2]
                    else: d_pap['Client'] = "CLIENT PAP"
                    frames_facture.append(d_pap)

            # --- CAS B : Onglet DÉCHÈTERIE (Feuil1, Header avec ID/net) ---
            else:
                # On scanne pour trouver l'en-tête "ID"
                d_scan = pd.read_excel(f_facture, sheet_name=sheet, header=None, nrows=10)
                h_idx_loc = 0
                for i, r in d_scan.iterrows():
                    if "ID" in str(r.values) and "net" in str(r.values):
                        h_idx_loc = i; break
                
                d_dech = pd.read_excel(f_facture, sheet_name=sheet, header=h_idx_loc)
                d_dech = d_dech.rename(columns={'ID': 'Num Ticket', 'lib_client': 'Client', 'lib_produit': 'Matière'})
                d_dech['Type_Flux'] = "DECHETTERIE"
                frames_facture.append(d_dech)

        if not frames_facture:
            raise ValueError("Aucun onglet valide trouvé dans la facture (Cherché 'PAP' ou colonnes 'ID/net')")

        df_facture = pd.concat(frames_facture, ignore_index=True)

        # === 3. CONVERSION ET NETTOYAGE FACTURE ===
        # Conversion KG -> Tonnes (CRUCIAL POUR DUPILLE)
        if 'net' in df_facture.columns:
            df_facture['Poids en Tonnes'] = pd.to_numeric(df_facture['net'], errors='coerce') / 1000
        
        df_facture['Num Ticket'] = pd.to_numeric(df_facture['Num Ticket'], errors='coerce')
        
        # Normalisation Matières
        df_terrain['Matière_Normalisée'] = df_terrain['Matière'].apply(normaliser_matiere)
        df_facture['Matière_Normalisée'] = df_facture['Matière'].apply(normaliser_matiere)

        # Conversion Date (Uniquement la date)
        col_date_t = next((c for c in df_terrain.columns if "date" in str(c).lower()), None)
        if col_date_t:
            df_terrain[col_date_t] = pd.to_datetime(df_terrain[col_date_t], dayfirst=True, errors='coerce').dt.date
            df_terrain = df_terrain.rename(columns={col_date_t: 'Date'})

        # Filtre Date (Optionnel)
        if var_activer_filtre.get():
            d_debut = cal_debut.get_date()
            d_fin = cal_fin.get_date()
            if 'Date' in df_terrain.columns:
                df_terrain = df_terrain[(df_terrain['Date'] >= d_debut) & (df_terrain['Date'] <= d_fin)]

        # === 4. CROISEMENT (MERGE) ===
        cols_ref = ['Num Ticket', 'Poids en Tonnes', 'Matière', 'Matière_Normalisée', 'Client', 'Type_Flux']
        # On s'assure que les colonnes existent
        for c in cols_ref:
            if c not in df_facture.columns: df_facture[c] = "INCONNU" if c != 'Poids en Tonnes' else 0

        df_analyse = pd.merge(
            df_terrain,
            df_facture[cols_ref],
            on='Num Ticket',
            suffixes=('_INT', '_EXT'),
            how='outer',
            indicator=True
        )

        # === 5. CALCULS ===
        df_ok = df_analyse[df_analyse['_merge'] == 'both'].copy()
        
        # Harmonisation des colonnes pour correspondre au format Valene
        if 'Date_INT' in df_ok.columns: df_ok['Date'] = df_ok['Date_INT']
        if 'Immatriculation' in df_ok.columns and 'Immatriculation_INT' not in df_ok.columns:
            df_ok['Immatriculation_INT'] = df_ok['Immatriculation']

        df_ok['Ecart'] = df_ok['Poids en Tonnes_INT'] - df_ok['Poids en Tonnes_EXT']
        
        # --- SELECTION COLONNES (FORMAT VALENE) ---
        cols_analyse = [
            'Date', 'Num Ticket', 'Client', 'TypeTournee', 'Immatriculation_INT',
            'Matière_INT', 'Matière_EXT', 
            'Poids en Tonnes_INT', 'Poids en Tonnes_EXT', 'Ecart'
        ]
        cols_analyse = [c for c in cols_analyse if c in df_ok.columns]
        
        rename_map = {
            'Immatriculation_INT': 'Immatriculation',
            'Matière_INT': 'Matière Terrain',
            'Matière_EXT': 'Matière Facture',
            'Poids en Tonnes_INT': 'Poids Terrain',
            'Poids en Tonnes_EXT': 'Poids Facture'
        }

        df_manquants = df_analyse[df_analyse['_merge'] == 'right_only'].copy()
        
        df_ecarts = df_ok[abs(df_ok['Ecart']) > 0.005].copy()
        df_ecarts = df_ecarts[cols_analyse].rename(columns=rename_map)
        
        df_alertes = df_ok[df_ok['Matière_Normalisée_INT'] != df_ok['Matière_Normalisée_EXT']].copy()
        df_alertes = df_alertes[cols_analyse].rename(columns=rename_map)

        # === 6. EXPORT EXCEL ===
        fichier_sortie = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="Resultat_DUPILLE.xlsx")
        if not fichier_sortie:
            bouton_lancer.config(text="Lancer l'analyse", state="normal")
            return

        with pd.ExcelWriter(fichier_sortie, engine='xlsxwriter') as writer:
            # Ecarts
            df_ecarts.to_excel(writer, sheet_name='Ecarts_Poids', index=False)
            auto_ajuster_colonnes(writer, df_ecarts, 'Ecarts_Poids')

            # Alertes
            df_alertes.to_excel(writer, sheet_name='Alertes_Matiere', index=False)
            auto_ajuster_colonnes(writer, df_alertes, 'Alertes_Matiere')

            # Bons Manquants
            cols_m_source = ['Date', 'Num Ticket', 'Client', 'Matière_EXT', 'Poids en Tonnes_EXT', 'Type_Flux']
            rename_m = {
                'Matière_EXT': 'Matière',
                'Poids en Tonnes_EXT': 'Poids Facture'
            }
            valid_m = [c for c in cols_m_source if c in df_manquants.columns]
            df_manquants_clean = df_manquants[valid_m].rename(columns=rename_m)
            
            df_manquants_clean.to_excel(writer, sheet_name='Bons_Manquants', index=False)
            auto_ajuster_colonnes(writer, df_manquants_clean, 'Bons_Manquants')

            # Synthèse Clients
            synthese_clients = df_ok.groupby('Client').agg({
                'Num Ticket': 'count', 'Poids en Tonnes_INT': 'sum', 'Poids en Tonnes_EXT': 'sum', 'Ecart': 'sum'
            }).reset_index()
            synthese_clients.to_excel(writer, sheet_name='Synthese_Clients', index=False)
            auto_ajuster_colonnes(writer, synthese_clients, 'Synthese_Clients')

            # Synthèses Par Flux (PAP vs DECHETTERIE)
            flux_list = df_ok['Type_Flux'].dropna().unique()
            for flux in flux_list:
                subset = df_ok[df_ok['Type_Flux'] == flux]
                nom_onglet = f"Synthese_{flux}"
                
                syn = subset.groupby('Matière_Normalisée_INT').agg({
                    'Num Ticket': 'count', 'Poids en Tonnes_INT': 'sum', 'Poids en Tonnes_EXT': 'sum', 'Ecart': 'sum'
                }).reset_index()
                
                syn.to_excel(writer, sheet_name=nom_onglet, index=False)
                auto_ajuster_colonnes(writer, syn, nom_onglet)

            # Rouge Conditionnel
            wb = writer.book
            fmt_rouge = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
            for sheet in writer.sheets:
                writer.sheets[sheet].conditional_format('A2:Z5000', {'type': 'formula', 'criteria': '=OR(A2="TOTAL GÉNÉRAL", AND(ISNUMBER(SEARCH("Ecart",A$1)), A2<0))', 'format': fmt_rouge})

        messagebox.showinfo("Succès", "Analyse DUPILLE terminée avec succès !")
        os.startfile(fichier_sortie)

    except Exception as e:
        messagebox.showerror("Erreur", f"Une erreur est survenue :\n{str(e)}")
    finally:
        bouton_lancer.config(text="Lancer l'analyse", state="normal")

# --- INTERFACE GRAPHIQUE ---

root = tk.Tk()
root.title("Analyse DUPILLE (KG -> Tonnes)")
root.geometry("600x450")
root.configure(bg="#f0f2f5")

# Styles
def ajout_champ(label_text):
    f = tk.Frame(root, bg="#f0f2f5")
    f.pack(pady=5, padx=20, fill="x")
    tk.Label(f, text=label_text, font=("Arial", 10, "bold"), bg="#f0f2f5", width=20, anchor="w").pack(side="left")
    e = tk.Entry(f, width=40)
    e.pack(side="left", padx=5)
    tk.Button(f, text="...", command=lambda: parcourir(e)).pack(side="left")
    return e

def parcourir(entry):
    f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
    if f:
        entry.delete(0, tk.END)
        entry.insert(0, f)

# Champs fichiers
frame_titre = tk.Frame(root, bg="#2c3e50", pady=10)
frame_titre.pack(fill="x")
tk.Label(frame_titre, text="Analyse DUPILLE", font=("Arial", 16, "bold"), fg="white", bg="#2c3e50").pack()

tk.Label(root, text="Sélectionnez vos fichiers :", bg="#f0f2f5", font=("Arial", 10)).pack(pady=(15, 5))

entree_terrain = ajout_champ("Fichier TERRAIN (LB) :")
entree_facture = ajout_champ("Fichier FACTURE :")

# Dates
frame_dates = tk.Frame(root, bg="#ecf0f1", bd=1, relief="solid")
frame_dates.pack(pady=20, padx=20, fill="x")

var_activer_filtre = tk.BooleanVar(value=False)
def toggle_dates():
    state = "normal" if var_activer_filtre.get() else "disabled"
    cal_debut.config(state=state)
    cal_fin.config(state=state)

tk.Checkbutton(frame_dates, text="Filtrer par date (Optionnel)", variable=var_activer_filtre, 
               command=toggle_dates, bg="#ecf0f1").pack(pady=5)

f_cal = tk.Frame(frame_dates, bg="#ecf0f1")
f_cal.pack(pady=5)
tk.Label(f_cal, text="Du :", bg="#ecf0f1").pack(side="left")
cal_debut = DateEntry(f_cal, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd/mm/yyyy')
cal_debut.pack(side="left", padx=5)
cal_debut.config(state="disabled")

tk.Label(f_cal, text="Au :", bg="#ecf0f1").pack(side="left")
cal_fin = DateEntry(f_cal, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd/mm/yyyy')
cal_fin.pack(side="left", padx=5)
cal_fin.config(state="disabled")

# Bouton
bouton_lancer = tk.Button(root, text="Lancer l'analyse", command=lancer_analyse, 
                          bg="#e67e22", fg="white", font=("Arial", 11, "bold"), height=2)
bouton_lancer.pack(fill="x", padx=40, pady=20)

# Auto-détection si le dossier INPUT existe
def auto_detect():
    if os.path.exists("INPUT/DUPILLE"):
        files = glob.glob("INPUT/DUPILLE/*.*")
        for f in files:
            nom = os.path.basename(f).lower()
            if "lb" in nom:
                entree_terrain.delete(0, tk.END)
                entree_terrain.insert(0, os.path.abspath(f))
            elif "dupille" in nom and "lb" not in nom:
                entree_facture.delete(0, tk.END)
                entree_facture.insert(0, os.path.abspath(f))

auto_detect()

root.mainloop()