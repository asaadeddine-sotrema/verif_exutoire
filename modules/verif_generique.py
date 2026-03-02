import pandas as pd
import streamlit as st
from datetime import datetime
import numpy as np
import logging
import unicodedata

logger = logging.getLogger(__name__)

def nettoyer_texte(texte):
    if pd.isna(texte): return ""
    txt = str(texte).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def convertir_date_robuste(val, assume_format="DD/MM/YYYY"):
    if pd.isna(val) or val == "": return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime.date)): 
        return val.date() if isinstance(val, pd.Timestamp) else val
    v_str = str(val).strip()
    try:
        dt = pd.to_datetime(v_str, dayfirst=(assume_format.startswith("DD")), errors='coerce')
        if pd.notna(dt): return dt.date()
    except: pass
    return pd.NaT

def check_client(row, col_int, col_ext):
    v_int = nettoyer_texte(row.get(col_int, ""))
    v_ext = nettoyer_texte(row.get(col_ext, ""))
    if not v_int or v_int == 'NAN': return 'Pb.Clt'
    if not v_ext or v_ext == 'NAN': return 'Pb.Clt'
    if v_int in v_ext or v_ext in v_int: return 'OK'
    return 'Pb.Clt'

def check_matiere(row, col_ext, col_int, presta):
    v_ext = nettoyer_texte(row.get(col_ext, ""))
    v_int = nettoyer_texte(row.get(col_int, ""))
    if not v_ext or not v_int or v_ext == 'NAN' or v_int == 'NAN': return 'Pb.Mat'
    # Generic logic: if one contains the other
    if v_int in v_ext or v_ext in v_int: return 'OK'
    return 'Pb.Mat'


logger = logging.getLogger(__name__)

def charger_prestataire_dynamique(f_terrain, f_facture, nom_prestataire, header_row, config):
    try:
        df_t = pd.read_excel(f_terrain)
    except Exception as e:
        st.error(f"Erreur de lecture du fichier Terrain : {e}")
        return None, None

    try:
        df_f = pd.read_excel(f_facture, header=header_row)
    except Exception as e:
        st.error(f"Erreur de lecture de la Facture {nom_prestataire} : {e}")
        return None, None
        
    df_t = df_t.dropna(how='all')
    df_f = df_f.dropna(how='all')
    
    mapping = config.get("mapping", {})
    options = config.get("options", {})
    
    # Validation des colonnes Facture requises
    cols_requises = []
    for k,v in mapping.items():
        if v and type(v) == str:
            cols_requises.append(v)
            
    colonnes_manquantes = [c for c in cols_requises if c not in df_f.columns]
    if colonnes_manquantes:
        st.error(f"Colonnes introuvables dans la Facture : {', '.join(colonnes_manquantes)}")
        st.info(f"Colonnes disponibles dans le fichier envoyé : {', '.join(df_f.columns)}")
        return None, None

    # Renommage canonique de la facture
    rename_dict = {
        mapping.get("Ticket"): "Num Ticket Facture",
        mapping.get("Date"): "Date",
        mapping.get("Poids"): "Poids_Facture",
        mapping.get("Client"): "EXT Client",
        mapping.get("Matiere"): "EXT_Matiere"
    }
    if "Bon" in mapping and mapping["Bon"]:
        rename_dict[mapping["Bon"]] = "Num Bon Facture"
    if "Immatriculation" in mapping and mapping["Immatriculation"]:
        rename_dict[mapping["Immatriculation"]] = "Immatriculation"
        
    # Enleve les clés None / Vides
    rename_dict = {k: v for k, v in rename_dict.items() if k and pd.notna(k) and str(k).strip() != ""}

    df_f = df_f.rename(columns=rename_dict)
    df_f['Exutoire'] = nom_prestataire
    
    # Nettoyage
    for col in ['Num Ticket Facture', 'Num Bon Facture']:
        if col in df_f.columns:
            df_f[col] = df_f[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
            
    if 'Immatriculation' in df_f.columns:
        df_f['Immatriculation'] = df_f['Immatriculation'].astype(str).apply(nettoyer_texte)
    
    # Date
    date_format = options.get("date_format", "DD/MM/YYYY")
    if 'Date' in df_f.columns:
        df_f['Date'] = df_f['Date'].apply(lambda x: convertir_date_robuste(x, assume_format=date_format))
        
    # Poids
    if 'Poids_Facture' in df_f.columns:
        df_f['Poids_Facture'] = pd.to_numeric(df_f['Poids_Facture'], errors='coerce').fillna(0)
        if options.get("poids_en_kilos", False):
            df_f['Poids_Facture'] = df_f['Poids_Facture'] / 1000.0
            
    # Terrain (Code Standardisé existant)
    rename_t = {
        'N° PESEE': 'Num Ticket Terrain',
        'DATE PESEE': 'Date_T',
        'N°BON DE VIDAGE': 'Num Bon Terrain',
        'POIDS NET': 'Poids_Terrain',
        'CODE DECHET': 'Matiere_T',
        'CODE CLIENT': 'INT Client',
        'IMMATRICULATION': 'Immatriculation_T'
    }
    df_t = df_t.rename(columns={k: v for k, v in rename_t.items() if k in df_t.columns})
    
    for col in ['Num Ticket Terrain', 'Num Bon Terrain']:
        if col in df_t.columns:
             df_t[col] = df_t[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
             
    if 'Immatriculation_T' in df_t.columns:
        df_t['Immatriculation_T'] = df_t['Immatriculation_T'].astype(str).apply(nettoyer_texte)
        
    if 'Date_T' in df_t.columns:
        df_t['Date_T'] = df_t['Date_T'].apply(lambda x: convertir_date_robuste(x))
    
    if 'Poids_Terrain' in df_t.columns:
        df_t['Poids_Terrain'] = pd.to_numeric(df_t['Poids_Terrain'], errors='coerce').fillna(0)
            
    return df_t, df_f

def process_generique(f_terrain, f_facture, nom_prestataire, header_row, config):
    df_t, df_f = charger_prestataire_dynamique(f_terrain, f_facture, nom_prestataire, header_row, config)
    if df_t is None or df_f is None: return pd.DataFrame()

    match_ticket = True
    match_bon = True
    
    col_ticket_t = 'Num Ticket Terrain'
    col_ticket_f = 'Num Ticket Facture'
    col_bon_t = 'Num Bon Terrain'
    col_bon_f = 'Num Bon Facture'
    
    # 1. Match Ticket
    df_f_restant = df_f.copy()
    matched_dfs = []
    
    if match_ticket:
        t_tickets = df_t[df_t[col_ticket_t].notna() & (df_t[col_ticket_t] != '') & (df_t[col_ticket_t] != 'NAN')]
        f_tickets = df_f_restant[df_f_restant[col_ticket_f].notna() & (df_f_restant[col_ticket_f] != '') & (df_f_restant[col_ticket_f] != 'NAN')]
        
        merged_ticket = pd.merge(t_tickets, f_tickets, left_on=col_ticket_t, right_on=col_ticket_f, how='inner')
        if not merged_ticket.empty:
            merged_ticket['Type_Match'] = 'Ticket'
            matched_dfs.append(merged_ticket)
            df_f_restant = df_f_restant[~df_f_restant[col_ticket_f].isin(merged_ticket[col_ticket_f])]
            
    # 2. Match Bon
    if match_bon and not df_f_restant.empty and col_bon_t in df_t.columns and col_bon_f in df_f_restant.columns:
        t_bons_unmatched = df_t[~df_t[col_ticket_t].isin(merged_ticket[col_ticket_t] if not merged_ticket.empty else [])]
        t_bons_unmatched = t_bons_unmatched[t_bons_unmatched[col_bon_t].notna() & (t_bons_unmatched[col_bon_t] != '') & (t_bons_unmatched[col_bon_t] != 'NAN')]
        f_bons = df_f_restant[df_f_restant[col_bon_f].notna() & (df_f_restant[col_bon_f] != '') & (df_f_restant[col_bon_f] != 'NAN')]
        
        merged_bon = pd.merge(t_bons_unmatched, f_bons, left_on=col_bon_t, right_on=col_bon_f, how='inner')
        if not merged_bon.empty:
            merged_bon['Type_Match'] = 'Bon'
            matched_dfs.append(merged_bon)
            df_f_restant = df_f_restant[~df_f_restant[col_bon_f].isin(merged_bon[col_bon_f])]
            
    df_final = pd.concat(matched_dfs, ignore_index=True) if matched_dfs else pd.DataFrame()
    
    if df_final.empty:
        st.warning("Aucune correspondance trouvée entre le Terrain et la Facture.")
        return df_final
        
    df_final['Num Ticket'] = df_final[col_ticket_t].fillna(df_final[col_ticket_f] if col_ticket_f in df_final.columns else '')
    df_final['Num Bon'] = df_final[col_bon_t] if col_bon_t in df_final.columns else ''
    
    df_final['Ecart'] = df_final['Poids_Terrain'] - df_final['Poids_Facture']
    df_final['Verif_Tonnes'] = np.where(df_final['Ecart'].abs() <= 0.01, 'OK', 'Pb.T')
    
    df_final['Verif_Client'] = df_final.apply(lambda row: check_client(row, 'INT Client', 'EXT Client'), axis=1)
    df_final['Verif_Matiere'] = df_final.apply(lambda row: check_matiere(row, 'EXT_Matiere', 'Matiere_T', nom_prestataire), axis=1)
    df_final['Verif_Exutoire'] = 'OK'
    
    cols_a_garder = ['Date', 'Num Ticket', 'Num Bon', 'Exutoire', 'INT Client', 'EXT Client', 'Matiere_T', 'EXT_Matiere', 'Immatriculation', 'Poids_Terrain', 'Poids_Facture', 'Ecart', 'Verif_Tonnes', 'Verif_Client', 'Verif_Matiere', 'Verif_Exutoire', 'Type_Match']
    
    for c in cols_a_garder:
        if c not in df_final.columns:
            df_final[c] = None

    return df_final[cols_a_garder]

# End of code
