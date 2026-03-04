import sys
import pandas as pd
sys.path.insert(0, '/home/amine/projects/verif_exutoire')
from modules.verif_satel import charger_satel_smirtom_enc

f_ter = "/home/amine/projects/77AC61D9_0F9A_24C5_A822_3DA2F09E9D00_20260303-1512.xls"
f_fac = "/home/amine/projects/SATEL SMIRTOM JANVIER 2026.xls"

with open(f_ter, 'rb') as t:
    df_ter = charger_satel_smirtom_enc(t)

df_ref_raw = pd.read_excel(f_fac, header=None, dtype=str)
header_row_idx = None
for i, row in df_ref_raw.iterrows():
    r_str = row.astype(str).str.lower().tolist()
    if any("num bon" in s for s in r_str) and any("nomclient" in s for s in r_str):
        header_row_idx = i; break

if header_row_idx is not None:
    df_ref = df_ref_raw.iloc[header_row_idx+1:].copy()
    df_ref.columns = df_ref_raw.iloc[header_row_idx]; df_ref.columns = df_ref.columns.astype(str)

ter_bon = set(df_ter['Num Ticket'].dropna().astype(str).str.strip())
ter_tp = set(df_ter['Num TP Manuel'].dropna().astype(str).str.strip())
fac_bon = set([str(x).strip() for x in df_ref['Num Bon'].dropna()])

print(f"Terrain Num Bon Count: {len(ter_bon)}")
print(f"Terrain Num TP Manuel Count: {len(ter_tp)}")
print(f"Facture Num Bon Count: {len(fac_bon)}")

print(f"Intersect Terrain Num Bon & Facture Num Bon: {len(ter_bon.intersection(fac_bon))}")
print(f"Intersect Terrain Num TP Manuel & Facture Num Bon: {len(ter_tp.intersection(fac_bon))}")
