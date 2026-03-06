import pandas as pd
from modules.verif_picheta import standardize_picheta_matiere, resolve_col

df = pd.DataFrame({
    'Matiere_T_T': ['TRANSPORT CARTONS', 'TRANSPORT FERRAILLES', 'TRANSPORT PLÂTRE', 'TRANSPORT DÉCHETS VÉGÉTAUX', 'GRAVATS', 'TRANSPORT DVE DIMANCHE & JOU', 'TRANSPORT CARTONS DIMANCHE'],
    'EXT_Matiere_F': ['DEPOT PAPIER CARTON TVA0 - BPU 4.7', 'DEPOT FERRAILLE TVA0 - BPU 4.6', 'DEPOT PLATRE TVA5.5 - BPU 4.8', 'DEPOT VEGETAUX TVA10 - BPU 4.2', 'DEPOT GRAVAT CHANTIER TVA10 - BPU 4.1', 'DEPOT VEGETAUX TVA10 - BPU 4.2', 'DEPOT PAPIER CARTON TVA0 - BPU 4.7']
})

df['Matiere_T'] = resolve_col(df, 'Matiere_T').fillna('GRAVATS').apply(standardize_picheta_matiere)
df['EXT_Matiere'] = resolve_col(df, 'EXT_Matiere').fillna('GRAVATS').apply(standardize_picheta_matiere)

print(df[['Matiere_T', 'EXT_Matiere']])
