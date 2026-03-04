import sys
import pandas as pd
import numpy as np

sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_valene import charger_valoseine

f_ter = "/home/amine/projects/C63CFD05_BA0B_D9C1_9A4F_C6AD08912B1A_20260303-1419.xls"

try:
    with open(f_ter, 'rb') as t:
        df = charger_valoseine(t)
        
    print("Terrain columns:", df.columns.tolist())
    if 'Date_Ref' in df.columns:
        print("Date_Ref head:")
        print(df['Date_Ref'].head())
    else:
        print("Date_Ref NOT FOUND in Fichier Terrain!")
except Exception as e:
    import traceback
    traceback.print_exc()
