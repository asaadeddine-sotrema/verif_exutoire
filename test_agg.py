import pandas as pd
import numpy as np

# Create a sample DF
df = pd.DataFrame({
    'Num Bon': ['123', '123'],
    'Num Ticket': ['A', 'B'],
    'Client': ['C1', 'C1'],
    'Poids_Facture': [10.5, 20.0]
})

df['AGG_BON'] = df['Num Bon'].astype(str).str.strip().str.upper().str.lstrip('0').replace(['NAN', '', 'NONE'], np.nan)
mask_bon = df['AGG_BON'].notna()
df_to_agg = df[mask_bon].copy()
df_rest = df[~mask_bon].copy()

p_col = 'Poids_Facture'
group_cols = ['AGG_BON']
group_cols = [c for c in group_cols if c in df_to_agg.columns]

agg_rules = {
    p_col: 'sum', 
    'Num Ticket': lambda x: ' / '.join(filter(None, [str(v) for v in sorted(list(set(x)))]))
}

for c in df_to_agg.columns:
    if c not in group_cols and c not in agg_rules and c != 'AGG_BON': 
        agg_rules[c] = 'first'

print("Agg rules before:", agg_rules)

try:
    df_agg = df_to_agg.groupby(group_cols, as_index=False).agg(agg_rules)
    print(df_agg)
except Exception as e:
    import traceback
    traceback.print_exc()
