import sys
import pandas as pd
f_fac = "/home/amine/projects/SATEL SMIRTOM JANVIER 2026.xls"
df_fac = pd.read_excel(f_fac, header=None)
for i in range(15):
    print(f"Row {i}:", df_fac.iloc[i].tolist())
