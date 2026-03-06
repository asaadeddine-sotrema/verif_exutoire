import pandas as pd
from modules.verif_dupille import process_dupille
import numpy as np

# Mocking data specifically to trace INT Client from start to finish
df_lb = pd.DataFrame({
    'Num Ticket': ['T1', 'T2'],
    'INT Client': ['C1_TER', 'C2_TER'],
    'Matiere_T': ['M1', 'M2'],
    'Poids_Terrain': [10.0, 20.0],
    'Date_Ref': ['2026-02-01', '2026-02-02']
})
df_fac = pd.DataFrame({
    'Num Ticket': ['T1', 'T3'],
    'EXT Client': ['C1_FAC', 'C3_FAC'],
    'EXT_Matiere': ['M1', 'M3'],
    'Poids_Facture': [10.0, 30.0],
    'Date_Ref': ['2026-02-01', '2026-02-03']
})

# simulate aggregate_dupille_df where nothing happens really because no Num Bon
def get_strict_key(row):
    t = str(row.get('Num Ticket', '')).strip().upper()
    if t in ['ST', 'NAN', '', 'NONE', '0', 'None', 'NAT']: return np.nan
    return t

df_lb['K'] = df_lb.apply(get_strict_key, axis=1)
df_fac['K'] = df_fac.apply(get_strict_key, axis=1)
df_lb['_TMP_ID'] = df_lb.index
df_fac['_TMP_ID'] = df_fac.index

m1 = pd.merge(df_lb.dropna(subset=['K']), df_fac.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
match1 = m1[m1['_merge'] == 'both'].copy(); match1['Methode'] = '1. Ticket Exact'

ids_t = match1['K'].unique()
ids_f = match1['K'].unique()

l_ter = df_lb[~df_lb['K'].isin(ids_t)].copy()
l_ref = df_fac[~df_fac['K'].isin(ids_f)].copy()

print("l_ter before rename:\n", l_ter.columns)

orph_t = l_ter.rename(columns={c: c + '_T' for c in df_lb.columns})
orph_t['_merge'] = 'left_only'
orph_t['Methode'] = 'Non Trouvé'

print("orph_t after rename:\n", orph_t.columns)

orph_f = l_ref.rename(columns={c: c + '_F' for c in df_fac.columns})
orph_f['_merge'] = 'right_only'
orph_f['Methode'] = 'Non Trouvé'

final = pd.concat([match1, orph_t, orph_f], ignore_index=True)

from modules.verif_dupille import resolve_col
final['INT Client'] = resolve_col(final, 'INT Client').fillna('').astype(str)
final['EXT Client'] = resolve_col(final, 'EXT Client').fillna(resolve_col(final, 'Client')).fillna('').astype(str)

print("final after concat:\n", final[['Num Ticket_T', 'Num Ticket_F', 'INT Client', 'EXT Client']])
