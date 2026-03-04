import sys
import pandas as pd
import numpy as np

sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_valene import process_valoseine

f_ter = "/home/amine/projects/C63CFD05_BA0B_D9C1_9A4F_C6AD08912B1A_20260303-1419.xls"
f_fac = "/home/amine/projects/VALOSEINE DECH TRIEL JANVIER 2026.xls"

try:
    with open(f_ter, 'rb') as t, open(f_fac, 'rb') as f:
        df = process_valoseine(t, f)
        
    print("Process returned Date head:")
    print(df['Date'].head(3))
    print("Is Date_Ref inside df?", 'Date_Ref' in df.columns)

    df_export = pd.DataFrame()
    if 'Date_Ref' in df.columns: df_export['Date'] = df['Date_Ref']
    elif 'Date' in df.columns: df_export['Date'] = df['Date']
    else: df_export['Date'] = pd.NaT

    print("df_export Date before to_datetime:")
    print(df_export['Date'].head(3))

    df_export['Date'] = pd.to_datetime(df_export['Date'], errors='coerce')

    df_export = df_export.astype(object).where(pd.notnull(df_export), None)

    print("df_export Date head after where notnull:")
    print(df_export['Date'].head(3))

except Exception as e:
    import traceback
    traceback.print_exc()
