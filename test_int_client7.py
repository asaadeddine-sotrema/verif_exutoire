import pandas as pd
from modules.verif_dupille import process_dupille
import numpy as np

f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"
f_fac = "/home/amine/projects/kpi_exploit_tablettes/Détail_K_Février_26.xlsx"

try:
    with open(f_lb, 'rb') as lb_f, open(f_fac, 'rb') as fac_f:
        df_final = process_dupille(lb_f, fac_f)
    print("Non-empty INT Client sum:", (df_final['INT Client'] != '').sum())
    print("Sample INT Client:")
    print(df_final['INT Client'].head())
    
    print("\nNon-empty EXT Client sum:", (df_final['EXT Client'] != '').sum())
    print("Sample EXT Client:")
    print(df_final['EXT Client'].head())
except Exception as e:
    print(e)
