import pandas as pd
import numpy as np
from app import resolve_col

# Mocking the dataframe logic from process_picheta_smirtom
df_ref = pd.DataFrame({
    0: ["Code Adresse: 12345", "Row1", "Row2", "Code Adresse: 67890", "Row3"],
    "Num Ticket": [np.nan, "T1", "T2", np.nan, "T3"],
    "date": [np.nan, "2024-01-01", "2024-01-02", np.nan, "2024-01-03"]
})

# Rename columns locally for test
cols_ref = {}
for c in df_ref.columns:
    cl = str(c).lower()
    if "date" in cl: cols_ref[c] = "Date_Ref"
df_ref = df_ref.rename(columns=cols_ref)

def extract_rupture(row):
    for v in row:
        s = str(v).strip()
        if s.lower().startswith("code adresse:"):
            return s.split(":", 1)[1].strip()
    return np.nan

df_ref['_rupture'] = df_ref.apply(extract_rupture, axis=1)
df_ref['_rupture'] = df_ref['_rupture'].ffill()

if 'TEMP_CodeAdresse' in df_ref.columns:
    df_ref['EXT Client'] = df_ref['TEMP_CodeAdresse'].replace(['', 'nan', 'NAN', 'None'], np.nan).fillna(df_ref['_rupture'])
else:
    df_ref['EXT Client'] = df_ref['_rupture']

mask_rupture = df_ref.apply(lambda r: any("code adresse:" in str(v).lower() for v in r), axis=1)
df_ref = df_ref[~mask_rupture].copy()

print("df_ref after rupture extraction:")
print(df_ref[['Num Ticket', '_rupture', 'EXT Client']])

# Simulate final concatenation
final = pd.DataFrame({
    'Num Ticket': ['T1', 'T2', 'T3'],
    'EXT Client_F': df_ref['EXT Client'].tolist()
})

print("\nFinal simulation:")
final['EXT Client'] = final.get('EXT Client_F', final.get('EXT Client', final.get('Client_F'))).fillna("DECHETERIE PICHETA SMIRTOM").astype(str).replace('', 'DECHETERIE PICHETA SMIRTOM')
print(final[['Num Ticket', 'EXT Client']])
