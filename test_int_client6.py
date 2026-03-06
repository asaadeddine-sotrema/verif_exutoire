import pandas as pd
from modules.verif_dupille import charger_dupille, process_dupille
import numpy as np

f_lb = "/home/amine/projects/kpi_exploit_tablettes/Détail_C_fevrier_26.xlsx"

with open(f_lb, 'rb') as lb_f:
    df_lb = charger_dupille(lb_f)
print("LB Columns exactly after load:", df_lb.columns)

