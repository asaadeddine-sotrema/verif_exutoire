import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def process_ecorec(f_ecorec, f_controle):
    """
    Rapproche les données de Ecorec avec les données d'un fichier contrôlé.
    Clé de jointure principale : 'Num Bon'.
    Retourne les anomalies de tonnage et les lignes orphelines.
    """
    logger.info("Début traitement Ecorec vs Contrôlé")
    
    try:
        # --- 1. Lecture et nettoyage Ecorec ---
        # Recherche dynamique de l'en-tête (la ligne qui contient "Num Bon" ou "TONNAGES")
        df_eco_temp = pd.read_excel(f_ecorec, header=None, nrows=20)
        header_idx_eco = 0
        for i, row in df_eco_temp.iterrows():
            row_str = str(row.values).lower()
            if "tonnages" in row_str or "num bon" in row_str:
                header_idx_eco = i
                break
                
        # On lit le fichier avec la bonne ligne d'en-tête
        # Comme stream a déjà été lu, on le remet à 0 s'il s'agit d'un objet file-like
        if hasattr(f_ecorec, 'seek'):
            f_ecorec.seek(0)
            
        df_eco = pd.read_excel(f_ecorec, header=header_idx_eco, dtype=str)
        
        # Nettoyage Colonnes Ecorec
        cols_eco_map = {}
        for c in df_eco.columns:
            cl = str(c).lower().strip()
            if "num bon" in cl: cols_eco_map[c] = "Num Bon"
            elif "tonnages" in cl: cols_eco_map[c] = "TONNAGES_Ecorec"
            elif "date" in cl and "jour" not in cl: cols_eco_map[c] = "Date"
            elif "nchantier" in cl: cols_eco_map[c] = "Client_Eco"
            elif "description" in cl: cols_eco_map[c] = "Matiere_Eco"
            elif "chauffeur" in cl: cols_eco_map[c] = "Chauffeur_Eco"
            elif "immatriculation" in cl: cols_eco_map[c] = "Immatriculation_Eco"
            elif "exutoire" in cl: cols_eco_map[c] = "Exutoire_Eco"
            elif "typecontenant" in cl: cols_eco_map[c] = "TypeContenant_Eco"
            
        df_eco = df_eco.rename(columns=cols_eco_map)
        
        # Gestion des ruptures / lignes vides Ecorec
        if "Num Bon" in df_eco.columns and "TONNAGES_Ecorec" in df_eco.columns:
            # Rejeter les lignes de sous-totaux ou vides (ex: où Num Bon est nul ou TONNAGES est vide)
             df_eco = df_eco.dropna(subset=['Num Bon', 'TONNAGES_Ecorec'])
             df_eco = df_eco[df_eco['Num Bon'].astype(str).str.strip() != '']
             df_eco = df_eco[df_eco['Num Bon'].astype(str).str.upper() != 'NAN']
             # Rejeter les lignes d'en-tête répétées
             df_eco = df_eco[df_eco['Num Bon'].astype(str).str.upper().str.strip() != 'NUM BON']
             df_eco = df_eco[df_eco['TONNAGES_Ecorec'].astype(str).str.strip() != '']
        else:
             logger.error("Colonnes 'Num Bon' ou 'TONNAGES' non trouvées dans Ecorec.")
             return pd.DataFrame()

        # Conversion Tonnages
        df_eco["TONNAGES_Ecorec"] = pd.to_numeric(df_eco["TONNAGES_Ecorec"], errors='coerce')
        
        # Nettoyage Clé Num Bon Ecorec
        df_eco['K'] = df_eco['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
        
        
        # --- 2. Lecture et nettoyage Contrôlé ---
        df_ctrl_temp = pd.read_excel(f_controle, header=None, nrows=20)
        header_idx_ctrl = 0
        for i, row in df_ctrl_temp.iterrows():
            row_str = str(row.values).lower()
            if "quantiteligne" in row_str or "num bon" in row_str:
                header_idx_ctrl = i
                break
                
        if hasattr(f_controle, 'seek'):
            f_controle.seek(0)
            
        df_ctrl = pd.read_excel(f_controle, header=header_idx_ctrl, dtype=str)
        
        # Nettoyage Colonnes Contrôlé
        cols_ctrl_map = {}
        for c in df_ctrl.columns:
            cl = str(c).lower().strip()
            if "num bon" in cl: cols_ctrl_map[c] = "Num Bon"
            elif "quantiteligne" in cl: cols_ctrl_map[c] = "TONNAGES_Contrôlé"
            elif "description" in cl: cols_ctrl_map[c] = "Matiere_Ctrl"
            elif "date" in cl and "jour" not in cl: cols_ctrl_map[c] = "Date"
            elif "chauffeur" in cl: cols_ctrl_map[c] = "Chauffeur_Ctrl"
            elif "immatriculation" in cl: cols_ctrl_map[c] = "Immatriculation_Ctrl"
            elif "exutoire" in cl: cols_ctrl_map[c] = "Exutoire_Ctrl"
            elif "typecontenant" in cl: cols_ctrl_map[c] = "TypeContenant_Ctrl"

        df_ctrl = df_ctrl.rename(columns=cols_ctrl_map)
        
        if "Num Bon" not in df_ctrl.columns or "TONNAGES_Contrôlé" not in df_ctrl.columns:
             logger.error("Colonnes 'Num Bon' ou 'QuantiteLigne' non trouvées dans fichier Contrôlé.")
             return pd.DataFrame()

        # Nettoyage données Contrôlé
        df_ctrl = df_ctrl.dropna(subset=['Num Bon'])
        df_ctrl = df_ctrl[df_ctrl['Num Bon'].astype(str).str.strip() != '']
        df_ctrl = df_ctrl[df_ctrl['Num Bon'].astype(str).str.upper() != 'NAN']
        df_ctrl = df_ctrl[df_ctrl['Num Bon'].astype(str).str.upper().str.strip() != 'NUM BON']
        df_ctrl["TONNAGES_Contrôlé"] = pd.to_numeric(df_ctrl["TONNAGES_Contrôlé"], errors='coerce')
        
        # Nettoyage Clé Num Bon Contrôlé
        df_ctrl['K'] = df_ctrl['Num Bon'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()


        # --- 3. Jointure (Merge) ---
        # On fait un outer merge pour repérer les manquants des deux côtés
        df_merge = pd.merge(df_eco, df_ctrl, on='K', how='outer', indicator=True, suffixes=('_Eco', '_Ctrl'))
        
        # On calcule l'écart de tonnage
        df_merge['Ecart'] = df_merge['TONNAGES_Ecorec'].fillna(0) - df_merge['TONNAGES_Contrôlé'].fillna(0)
        
        # Typologie d'erreur
        def determine_statut(row):
             if row['_merge'] == 'left_only':
                 return 'Présent dans Ecorec, Manquant dans Contrôlé'
             elif row['_merge'] == 'right_only':
                 return 'Présent dans Contrôlé, Manquant dans Ecorec'
             elif abs(row['Ecart']) >= 0.01:  # Tolérance de 0.01T
                 return 'Écart de Tonnage'
             else:
                 return 'OK'
                 
        df_merge['Statut'] = df_merge.apply(determine_statut, axis=1)
        
        # Consolidation des infos
        df_merge['Num Bon'] = df_merge['Num Bon_Eco'].fillna(df_merge['Num Bon_Ctrl'])
        
        df_merge['Date'] = df_merge['Date_Eco'].fillna(df_merge['Date_Ctrl'])
        # Nettoyage Date
        df_merge['Date'] = pd.to_datetime(df_merge['Date'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
        
        df_merge['Client'] = df_merge.get('Client_Eco', pd.Series(index=df_merge.index, dtype='object'))
        df_merge['Matiere'] = df_merge['Matiere_Eco'].fillna(df_merge['Matiere_Ctrl'])
        
        # Ajout des nouvelles colonnes
        df_merge['Chauffeur'] = df_merge.get('Chauffeur_Eco', pd.Series(index=df_merge.index, dtype='object')).fillna(df_merge.get('Chauffeur_Ctrl', ''))
        df_merge['Immatriculation'] = df_merge.get('Immatriculation_Eco', pd.Series(index=df_merge.index, dtype='object')).fillna(df_merge.get('Immatriculation_Ctrl', ''))
        df_merge['Exutoire'] = df_merge.get('Exutoire_Eco', pd.Series(index=df_merge.index, dtype='object')).fillna(df_merge.get('Exutoire_Ctrl', ''))
        df_merge['Type Contenant'] = df_merge.get('TypeContenant_Eco', pd.Series(index=df_merge.index, dtype='object')).fillna(df_merge.get('TypeContenant_Ctrl', ''))
        
        cols_final = ['Statut', 'Date', 'Num Bon', 'Client', 'Exutoire', 'Chauffeur', 'Immatriculation', 'Type Contenant', 'Matiere', 'TONNAGES_Ecorec', 'TONNAGES_Contrôlé', 'Ecart']
        df_final = df_merge[[c for c in cols_final if c in df_merge.columns]].copy()
        
        # Remplacer les NaN par des espaces vides pour un affichage plus propre
        df_final = df_final.fillna('')
        
        # Pour une meilleure lisibilité, on trie par statut d'abord (Anomalies en haut)
        df_final['is_anomaly'] = df_final['Statut'] != 'OK'
        df_final = df_final.sort_values(by=['is_anomaly', 'Date', 'Num Bon'], ascending=[False, True, True])
        df_final = df_final.drop(columns=['is_anomaly'])
        
        return df_final

    except Exception as e:
        logger.error(f"Erreur process Ecorec: {e}", exc_info=True)
        return pd.DataFrame([{"Erreur": str(e)}])

