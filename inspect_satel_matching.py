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
else:
    df_ref = df_ref_raw

print("Terrain Num Ticket head:")
print(df_ter['Num Ticket'].head(10).tolist())
if 'Num TP Manuel' in df_ter.columns:
    print("Terrain Num TP Manuel head:")
    print(df_ter['Num TP Manuel'].head(10).tolist())

print("\nFacture headers:", df_ref.columns.tolist())
try:
    print("Facture Num Bon head:")
    print(df_ref[[c for c in df_ref.columns if 'bon' in c.lower()]].head(10))
    print("Facture Ticket head:")
    print(df_ref[[c for c in df_ref.columns if 'ticket' in c.lower()]].head(10))
except Exception as e:
    pass
