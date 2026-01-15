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
    
    termes_om = ["DECHETS INDUSTRIELS", "ORDURES MENAGERES", "DIB", "O.M"]
    if any(x in valeur_clean for x in termes_om):
        return "ORDURES MENAGERES"
        
    termes_emb = ["EMBALLAGES MENAGERS", "RECYCLABLES", "TRI SELECTIF"]
    if any(x in valeur_clean for x in termes_emb):
        return "EMBALLAGES MENAGERS RECUPEREES"
        
    if "VERRE" in valeur_clean: return "VERRE"
    if "CARTON" in valeur_clean: return "CARTON"

    return valeur_clean

def trouver_ligne_en_tete(chemin_fichier, mot_cle):
    try:
        df_temp = pd.read_excel(chemin_fichier, header=None, nrows=30)
        for index, row in df_temp.iterrows():
            texte_ligne = " ".join(row.astype(str).values).lower()
            if mot_cle.lower() in texte_ligne:
                return index
        return 0
    except Exception:
        return 0

def detecter_fichiers_source():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, "Source", "VALENE")
    paths = {}
    
    if not os.path.exists(target_dir):
        return paths

    fichiers = glob.glob(os.path.join(target_dir, "*.xls*"))
    
    for f in fichiers:
        nom = os.path.basename(f).upper()
        if nom.startswith("~$"): continue

        if "PAP" in nom and "VALENE" in nom: paths['pap'] = f
        elif "PAV" in nom and "VALENE" in nom: paths['pav'] = f
        elif "SOTREMA2" in nom or ("SOTREMA" in nom and "VALENE" in nom): paths['sotrema'] = f
        elif "EXPORT" in nom or "RPT" in nom: paths['ref'] = f
    return paths

def lancer_analyse(fichiers_input=None, options_input=None):
    mode_gui = fichiers_input is None

    if mode_gui:
        f_pap = entree_pap.get()
        f_pav = entree_pav.get()
        f_sotrema = entree_sotrema.get()
        f_ref = entree_ref.get()
        
        activer_filtre = var_activer_filtre.get()
        date_debut_str = cal_debut.get()
        date_fin_str = cal_fin.get()
    else:
        f_pap = fichiers_input.get('pap')
        f_pav = fichiers_input.get('pav')
        f_sotrema = fichiers_input.get('sotrema')
        f_ref = fichiers_input.get('ref')
        activer_filtre = options_input.get('filtre', False)
        date_debut_str = options_input.get('date_debut', "")
        date_fin_str = options_input.get('date_fin', "")

    if not all([f_pap, f_pav, f_sotrema, f_ref]):
        msg = "Il manque des fichiers ! Vérifiez que les 4 champs sont remplis."
        if mode_gui: messagebox.showwarning("Attention", msg)
        else: print(msg)
        return

    if mode_gui:
        bouton_lancer.config(text="Traitement en cours...", state="disabled")
        root.update()
    else:
        print("Traitement en cours...")

    try:
        # 1. IMPORTATION
        header_ref = trouver_ligne_en_tete(f_ref, 'N° de pesée')
        df_ref = pd.read_excel(f_ref, header=header_ref)

        df_pap = pd.read_excel(f_pap, header=trouver_ligne_en_tete(f_pap, 'Description'))
        df_pav = pd.read_excel(f_pav, header=trouver_ligne_en_tete(f_pav, 'Description'))
        df_sotrema = pd.read_excel(f_sotrema, header=trouver_ligne_en_tete(f_sotrema, 'Description'))

        # 2. PREPARATION TERRAIN
        cols_utiles = ['Date', 'Num Ticket', 'Poids en Tonnes', 'Num Bon', 'Description', 'Immatriculation']
        
        # Patch noms colonnes
        for df in [df_pap, df_pav, df_sotrema]:
            if 'Poids Net' in df.columns and 'Poids en Tonnes' not in df.columns:
                df.rename(columns={'Poids Net': 'Poids en Tonnes'}, inplace=True)
            if 'Immatriculation' not in df.columns:
                df['Immatriculation'] = ''

        def safe_select(df, cols):
            valid_cols = [c for c in cols if c in df.columns]
            return df[valid_cols].copy()

        df_pap = safe_select(df_pap, cols_utiles)
        df_pav = safe_select(df_pav, cols_utiles)
        df_sotrema = safe_select(df_sotrema, cols_utiles)

        df_pap = df_pap.rename(columns={'Description' : 'Matière'})
        df_pav = df_pav.rename(columns={'Description' : 'Matière'})
        df_sotrema = df_sotrema.rename(columns={'Description' : 'Matière'})

        df_pap['TypeTournee'] = 'PAP'
        df_pav['TypeTournee'] = 'PAV'
        df_sotrema['TypeTournee'] = 'SOTREMA2'

        df_terrain = pd.concat([df_pap, df_pav, df_sotrema], ignore_index=True)
        df_terrain = df_terrain.dropna(subset=['Num Ticket'])
        df_terrain['Num Ticket'] = pd.to_numeric(df_terrain['Num Ticket'], errors='coerce')
        df_terrain['Date'] = pd.to_datetime(df_terrain['Date'], dayfirst=True, errors='coerce').dt.date
        df_terrain['Matière_Normalisée'] = df_terrain['Matière'].apply(normaliser_matiere)

        # 3. PREPARATION REFERENCE
        cols_ref = ['N° de pesée', 'Date d\'entrée', 'Poids de la matière', 'Matière réalisée', 'Client', 'Immatriculation']
        cols_ref = [c for c in cols_ref if c in df_ref.columns]
        df_ref = df_ref[cols_ref].copy()
        
        df_ref = df_ref.rename(columns={'N° de pesée': 'Num Ticket', 'Poids de la matière': 'Poids en Tonnes', 'Matière réalisée': 'Matière'})
        df_ref['Num Ticket'] = pd.to_numeric(df_ref['Num Ticket'], errors='coerce')
        df_ref["Date d'entrée"] = pd.to_datetime(df_ref["Date d'entrée"], dayfirst=True, errors='coerce').dt.date
        df_ref['Matière_Normalisée'] = df_ref['Matière'].apply(normaliser_matiere)

        # Normalisation Clients
        if 'Client' in df_ref.columns:
            remplacement_clients = {
                "CU GRAND PARIS SEINE ET OISE - AUBE": "GPSO",
                "SOTREMA - ROSNY SUR SEINE - SIEGE": "SOTREMA"
            }
            df_ref['Client'] = df_ref['Client'].replace(remplacement_clients)

        # 4. FILTRAGE DATE
        if activer_filtre:
            d_debut = pd.to_datetime(date_debut_str, dayfirst=True).date()
            d_fin = pd.to_datetime(date_fin_str, dayfirst=True).date()
            df_terrain = df_terrain[(df_terrain['Date'] >= d_debut) & (df_terrain['Date'] <= d_fin)]
            df_ref = df_ref[(df_ref["Date d'entrée"] >= d_debut) & (df_ref["Date d'entrée"] <= d_fin)]

        # 5. CROISEMENT
        df_analyse = pd.merge(df_terrain, df_ref, on='Num Ticket', suffixes=('_INT', '_EXT'), how='inner')
        df_analyse['Ecart'] = df_analyse['Poids en Tonnes_INT'] - df_analyse['Poids en Tonnes_EXT']

        # 6. ANOMALIES
        # --- SELECTION DES COLONNES UTILES ---
        cols_analyse = [
            'Date', 'Num Ticket', 'Client', 'TypeTournee', 'Immatriculation_INT',
            'Matière_INT', 'Matière_EXT', 
            'Poids en Tonnes_INT', 'Poids en Tonnes_EXT', 'Ecart'
        ]
        # Sécurité : on ne garde que les colonnes qui existent vraiment
        cols_analyse = [c for c in cols_analyse if c in df_analyse.columns]
        
        # Renommage pour un Excel plus propre
        rename_map = {
            'Immatriculation_INT': 'Immatriculation',
            'Matière_INT': 'Matière Terrain',
            'Matière_EXT': 'Matière Facture',
            'Poids en Tonnes_INT': 'Poids Terrain',
            'Poids en Tonnes_EXT': 'Poids Facture'
        }

        df_ecarts = df_analyse[abs(df_analyse['Ecart']) > 0.001].copy()
        df_ecarts = df_ecarts[cols_analyse].rename(columns=rename_map)

        df_conflits = df_analyse[df_analyse['Matière_Normalisée_INT'] != df_analyse['Matière_Normalisée_EXT']].copy()
        df_conflits = df_conflits[cols_analyse].rename(columns=rename_map)

        # Pour les manquants (basé sur la facture uniquement)
        cols_manquants = ['Date d\'entrée', 'Num Ticket', 'Client', 'Matière', 'Poids en Tonnes', 'Immatriculation']
        cols_manquants = [c for c in cols_manquants if c in df_ref.columns]

        tickets_terrain = set(df_terrain['Num Ticket'].dropna())
        df_manquants = df_ref[~df_ref['Num Ticket'].isin(tickets_terrain)].copy()
        df_manquants = df_manquants[cols_manquants].rename(columns={'Date d\'entrée': 'Date'})

        # 7. SYNTHESES
        syntheses = {}
        for tournee in ['PAP', 'PAV', 'SOTREMA2']:
            df_t = df_analyse[df_analyse['TypeTournee'] == tournee].copy()
            if not df_t.empty:
                df_t['Erreur_Poids'] = (abs(df_t['Ecart']) > 0.001).astype(int)
                synthese = df_t.groupby('Matière_Normalisée_INT').agg({
                    'Num Ticket': 'count', 'Erreur_Poids': 'sum', 
                    'Poids en Tonnes_INT': 'sum', 'Poids en Tonnes_EXT': 'sum', 'Ecart': 'sum'
                }).reset_index()
                synthese.columns = ['Matière Standard', 'Total Tickets', 'Tickets Erreur', 'Tonnage Terrain', 'Tonnage Facturé', 'Ecart Total']
                synthese = synthese.round(3)
                syntheses[tournee] = synthese

        if 'Client' in df_analyse.columns:
            synthese_clients = df_analyse.groupby('Client').agg({
                'Num Ticket': 'count', 'Poids en Tonnes_INT': 'sum', 'Poids en Tonnes_EXT': 'sum', 'Ecart': 'sum'
            }).reset_index()
            synthese_clients.columns = ['Client', 'Nb Tickets', 'Tonnage INT', 'Tonnage EXT', 'Ecart Total']
            synthese_clients = synthese_clients.round(3)
        else:
            synthese_clients = pd.DataFrame()

        # 8. EXPORT
        nom_fichier = "Resultat_Analyse.xlsx"
        if activer_filtre: nom_fichier = f"Analyse_{date_debut_str.replace('/','-')}.xlsx"

        if mode_gui:
            chemin = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=nom_fichier)
        else:
            chemin = os.path.abspath(nom_fichier)

        if chemin:
            with pd.ExcelWriter(chemin, engine='xlsxwriter') as writer:
                df_ecarts.to_excel(writer, sheet_name='Ecarts_Poids', index=False)
                df_conflits.to_excel(writer, sheet_name='Alertes_Matiere', index=False)
                df_manquants.to_excel(writer, sheet_name='Bons_Manquants', index=False)
                synthese_clients.to_excel(writer, sheet_name='Synthese_Clients', index=False)
                
                if 'PAP' in syntheses: syntheses['PAP'].to_excel(writer, sheet_name='Synthese_PAP', index=False)
                if 'PAV' in syntheses: syntheses['PAV'].to_excel(writer, sheet_name='Synthese_PAV', index=False)
                if 'SOTREMA2' in syntheses: syntheses['SOTREMA2'].to_excel(writer, sheet_name='Synthese_SOTREMA2', index=False)

                wb = writer.book
                fmt_rouge = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                ws_clients = writer.sheets['Synthese_Clients']
                ws_clients.conditional_format('E2:E100', {'type': 'cell', 'criteria': '!=', 'value': 0, 'format': fmt_rouge})

                # Ajustement automatique des colonnes
                liste_feuilles = [
                    (df_ecarts, 'Ecarts_Poids'),
                    (df_conflits, 'Alertes_Matiere'),
                    (df_manquants, 'Bons_Manquants'),
                    (synthese_clients, 'Synthese_Clients')
                ]
                if 'PAP' in syntheses: liste_feuilles.append((syntheses['PAP'], 'Synthese_PAP'))
                if 'PAV' in syntheses: liste_feuilles.append((syntheses['PAV'], 'Synthese_PAV'))
                if 'SOTREMA2' in syntheses: liste_feuilles.append((syntheses['SOTREMA2'], 'Synthese_SOTREMA2'))

                for df, sheet_name in liste_feuilles:
                    worksheet = writer.sheets[sheet_name]
                    for idx, col in enumerate(df.columns):
                        max_len = len(str(col)) + 2
                        if not df.empty:
                            max_data = df[col].astype(str).map(len).max()
                            if pd.notna(max_data):
                                max_len = max(max_len, max_data + 2)
                        worksheet.set_column(idx, idx, min(max_len, 60))

            if mode_gui:
                messagebox.showinfo("Succès", f"Fichier généré :\n{chemin}")
                os.startfile(chemin)
            else:
                print(f"Succès : Fichier généré : {chemin}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        if mode_gui: messagebox.showerror("Erreur", f"Erreur :\n{e}")
        else: print(f"Erreur : {e}")
    finally:
        if mode_gui:
            bouton_lancer.config(text="Lancer l'analyse", state="normal")

# --- INTERFACE GRAPHIQUE ---

def toggle_dates():
    etat = "normal" if var_activer_filtre.get() else "disabled"
    cal_debut.config(state=etat)
    cal_fin.config(state=etat)

def parcourir(entry):
    f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
    if f:
        entry.delete(0, tk.END)
        entry.insert(0, f)

if __name__ == "__main__" and "--auto" in sys.argv:
    print("Mode automatique activé.")
    paths = detecter_fichiers_source()
    if len(paths) < 4:
        print("Erreur: Tous les fichiers n'ont pas été trouvés dans Source/VALENE.")
        print(f"Trouvés: {list(paths.keys())}")
    else:
        lancer_analyse(fichiers_input=paths, options_input={'filtre': False})
    sys.exit()

root = tk.Tk()
root.title("Outil Contrôle Tonnage")
root.geometry("600x650")

tk.Label(root, text="Fichiers Sources (Dossier: Source/VALENE)", font=("Arial", 12, "bold")).pack(pady=10)
frame_fichiers = tk.Frame(root)
frame_fichiers.pack(padx=20)

def ajout_champ(lbl):
    f = tk.Frame(frame_fichiers)
    f.pack(fill="x", pady=2)
    tk.Label(f, text=lbl, width=20, anchor='w').pack(side="left")
    e = tk.Entry(f, width=40)
    e.pack(side="left", padx=5)
    tk.Button(f, text="...", command=lambda: parcourir(e)).pack(side="left")
    return e

entree_pap = ajout_champ("Fichier PAP :")
entree_pav = ajout_champ("Fichier PAV :")
entree_sotrema = ajout_champ("Fichier SOTREMA 2 :")
tk.Label(frame_fichiers, text="---").pack()
entree_ref = ajout_champ("Fichier EXPORT :")

frame_dates = tk.Frame(root, bg="#ecf0f1", bd=1, relief="solid")
frame_dates.pack(pady=20, padx=20, fill="x")

var_activer_filtre = tk.BooleanVar(value=False)
tk.Checkbutton(frame_dates, text="Filtrer par date", variable=var_activer_filtre, 
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

bouton_lancer = tk.Button(root, text="Lancer l'analyse", command=lancer_analyse, 
                          bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), height=2)
bouton_lancer.pack(fill="x", padx=40, pady=20)

lbl_info = tk.Label(root, text="Recherche dans Source/VALENE...", fg="gray")
lbl_info.pack(pady=5)

# --- FONCTION DE DETECTION CIBLÉE ---

def remplissage_auto():
    paths = detecter_fichiers_source()
    
    if not paths:
        lbl_info.config(text="Dossier 'Source/VALENE' introuvable !", fg="red")
        return

    if 'pap' in paths: entree_pap.delete(0, tk.END); entree_pap.insert(0, paths['pap'])
    if 'pav' in paths: entree_pav.delete(0, tk.END); entree_pav.insert(0, paths['pav'])
    if 'sotrema' in paths: entree_sotrema.delete(0, tk.END); entree_sotrema.insert(0, paths['sotrema'])
    if 'ref' in paths: entree_ref.delete(0, tk.END); entree_ref.insert(0, paths['ref'])
    
    compteur = len(paths)
    
    if compteur > 0:
        lbl_info.config(text=f"{compteur} fichiers trouvés dans Source/VALENE", fg="green")
    else:
        lbl_info.config(text="Aucun fichier correspondant dans Source/VALENE", fg="red")

root.after(100, remplissage_auto)
root.mainloop()