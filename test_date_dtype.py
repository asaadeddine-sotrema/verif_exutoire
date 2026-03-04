import sys
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_valene import process_valoseine
import pandas as pd

f_ter = "/home/amine/projects/C63CFD05_BA0B_D9C1_9A4F_C6AD08912B1A_20260303-1419.xls"
f_fac = "/home/amine/projects/VALOSEINE DECH TRIEL JANVIER 2026.xls"

try:
    with open(f_ter, 'rb') as t, open(f_fac, 'rb') as f:
        df = process_valoseine(t, f)
        
    print(df['Date'].head(5))
    print(df['Date'].apply(type).head(5))
except Exception as e:
    import traceback
    traceback.print_exc()
