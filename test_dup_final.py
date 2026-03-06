import pandas as pd
from modules.verif_dupille import process_dupille
import logging
logging.basicConfig(level=logging.INFO)

f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"
f_fac = "/home/amine/projects/kpi_exploit_tablettes/Détail_K_Février_26.xlsx"

try:
    with open(f_lb, 'rb') as lb_f, open(f_fac, 'rb') as fac_f:
        df_final = process_dupille(lb_f, fac_f)
    print("Columns:", df_final.columns)
    print("First 5 lines of INT Client and EXT Client:")
    print(df_final[['INT Client', 'EXT Client']].head())
    print("Non-empty INT Client sum:", (df_final['INT Client'] != '').sum())
    print("Non-empty EXT Client sum:", (df_final['EXT Client'] != '').sum())
except Exception as e:
    import traceback
    traceback.print_exc()
