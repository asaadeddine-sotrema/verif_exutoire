import pandas as pd
from app import resolve_col

df = pd.DataFrame({
    'Matiere_T_T': ['T1', 'T2', None, 'T4'],
    'EXT_Matiere_F': [None, 'F2', 'F3', 'F4'],
    '_merge': ['left_only', 'both', 'right_only', 'both']
})

print("Before resolve:")
print(df)
df['Matiere_T'] = resolve_col(df, 'Matiere_T')
ext_mat = df.get('EXT_Matiere', df.get('EXT_Matiere_F', pd.Series([None]*len(df))))
df['EXT_Matiere'] = ext_mat

print("\nAfter resolve:")
print(df[['_merge', 'Matiere_T', 'EXT_Matiere']])
