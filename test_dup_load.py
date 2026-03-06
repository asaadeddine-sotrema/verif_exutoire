import pandas as pd
from modules.verif_dupille import charger_dupille, charger_dupille_facture

f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"
f_fac = "/home/amine/projects/kpi_exploit_tablettes/Détail_K_Février_26.xlsx"

with open(f_lb, 'rb') as lb_f:
    df_lb = charger_dupille(lb_f)
print("LB Columns:", df_lb.columns)

with open(f_fac, 'rb') as fac_f:
    df_fac = charger_dupille_facture(fac_f)
print("FAC Columns:", df_fac.columns)
