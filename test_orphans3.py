import pandas as pd
from app import resolve_col

df = pd.DataFrame({
    'Matiere_T_T': ['T1', 'T2', None, 'T4'],
    'EXT_Matiere_F': [None, 'F2', 'F3', 'F4'],
    '_merge': ['left_only', 'both', 'right_only', 'both']
})

print("Testing resolve_col logic directly...")
fallback = pd.Series([None] * len(df), index=df.index)
print("EXT_Matiere_T:", df.get("EXT_Matiere_T", fallback).tolist())
print("EXT_Matiere_F:", df.get("EXT_Matiere_F", fallback).tolist())

res = resolve_col(df, "EXT_Matiere")
print("resolve_col:", res.tolist())

print("\nWhat about Matiere_T?")
print(resolve_col(df, "Matiere_T").tolist())

