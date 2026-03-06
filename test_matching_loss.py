import pandas as pd
import numpy as np
from modules.verif_dupille import process_dupille, resolve_col

def run_test():
    # T1 will match
    # T2 is terrain only
    # T3 is facture only
    df_lb = pd.DataFrame({
        'Num Ticket': ['T1', 'T2'],
        'Tournée modèle': ['TM_1', 'TM_2'],
        'Poids_Terrain': [10.0, 20.0],
        'Date_Ref': ['2026-02-01', '2026-02-02']
    })
    df_fac = pd.DataFrame({
        'Num Ticket': ['T1', 'T3'],
        'Client': ['C1_FAC', 'C3_FAC'], # In reality, maybe this is 'EXT Client' after rename
        'Poids_Facture': [10.0, 30.0],
        'Date_Ref': ['2026-02-01', '2026-02-03']
    })
    
    # In process_dupille, df_fac gets renamed.
    # Let's simulate the rename for df_fac
    df_fac = df_fac.rename(columns={'Client': 'EXT Client'})

    df_lb['K'] = df_lb['Num Ticket']
    df_fac['K'] = df_fac['Num Ticket']
    df_lb['_TMP_ID'] = df_lb.index
    df_fac['_TMP_ID'] = df_fac.index
    
    # Matching
    m1 = pd.merge(df_lb.dropna(subset=['K']), df_fac.dropna(subset=['K']), on='K', how='outer', indicator=True, suffixes=('_T', '_F'))
    match1 = m1[m1['_merge'] == 'both'].copy()
    match1['Methode'] = '1. Ticket Exact'

    # Orphans
    ids_t = match1['K'].unique()
    ids_f = match1['K'].unique()
    l_ter = df_lb[~df_lb['K'].isin(ids_t)].copy()
    l_ref = df_fac[~df_fac['K'].isin(ids_f)].copy()

    orph_t = l_ter.rename(columns={c: c + '_T' for c in df_lb.columns})
    orph_t['_merge'] = 'left_only'
    orph_t['Methode'] = 'Non Trouvé'

    orph_f = l_ref.rename(columns={c: c + '_F' for c in df_fac.columns})
    orph_f['_merge'] = 'right_only'
    orph_f['Methode'] = 'Non Trouvé'

    final = pd.concat([match1, orph_t, orph_f], ignore_index=True)
    
    print("Columns in final:\n", final.columns.tolist())
    
    # The resolution logic
    final['INT Client'] = resolve_col(final, 'INT Client').fillna(resolve_col(final, 'Tournée modèle')).fillna(resolve_col(final, 'Client')).fillna('').astype(str)
    final['EXT Client'] = resolve_col(final, 'EXT Client').fillna(resolve_col(final, 'Client')).fillna('').astype(str)

    print("\nResults:")
    print(final[['Num Ticket_T', 'Num Ticket_F', 'INT Client', 'EXT Client', '_merge']])

run_test()
