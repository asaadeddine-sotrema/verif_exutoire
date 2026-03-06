import pandas as pd
from modules.verif_dupille import charger_dupille, charger_dupille_facture
import numpy as np

f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"
f_fac = "/home/amine/projects/kpi_exploit_tablettes/Détail_K_Février_26.xlsx"

with open(f_lb, 'rb') as lb_f:
    df_lb = charger_dupille(lb_f)
print("LB Columns:", df_lb.columns)
if 'INT Client' in df_lb:
    print("INT Client head LB:", df_lb['INT Client'].head())

with open(f_fac, 'rb') as fac_f:
    df_fac = charger_dupille_facture(fac_f)
    nc = {}
    for c in df_fac.columns:
        cl = str(c).lower().strip()
        if "ticket" in cl or cl == "id": nc[c] = "Num Ticket"
        elif "net" in cl or ("poids" in cl and "facture" in cl): nc[c] = "Poids_Facture" 
        elif "zone" in cl or "lib_zone" in cl: nc[c] = "EXT Client"
        elif "client" in cl or "lib_client" in cl: nc[c] = "Ref_Client"
        elif "code matière" in cl or "lib_produit" in cl or "matière" in cl or "produit" in cl: nc[c] = "EXT_Matiere"
        elif "immatriculation" in cl or "véhicule" in cl: nc[c] = "Immatriculation"
        elif "transporteur" in cl or "lib_transporteur" in cl: nc[c] = "Transporteur"
        elif "bordereau" in cl or "bon de" in cl or (cl.startswith("n") and cl.endswith("bon")) or "n° bon" in cl or "num bon" in cl or "bon n" in cl: nc[c] = "Num Bon"
        elif "date" in cl or "dates" in cl: nc[c] = "Date_Ref"
        elif "original_sheet_name" in cl: nc[c] = "Activité"
    df_fac = df_fac.rename(columns=nc)
print("FAC Columns:", df_fac.columns)
if 'EXT Client' in df_fac:
    print("EXT Client head FAC:", df_fac['EXT Client'].head())

