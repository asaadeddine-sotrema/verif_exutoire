import pandas as pd

def standardize_picheta_matiere(val):
    if pd.isna(val) or str(val).strip() == "":
        return val
    v = str(val).lower()
    
    if 'végétaux' in v or 'vegetaux' in v or 'dve' in v:
        return 'DEPOT VEGETAUX TVA10 - BPU 4.2'
    if 'carton' in v:
        return 'DEPOT PAPIER CARTON TVA0 - BPU 4.7'
    if 'gravat' in v:
        return 'DEPOT GRAVAT CHANTIER TVA10 - BPU 4.1'
    if 'plâtre' in v or 'platre' in v:
        return 'DEPOT PLATRE TVA5.5 - BPU 4.8'
    if 'ferraille' in v or 'ferrailles' in v:
        return 'DEPOT FERRAILLE TVA5.5 - BPU 4.8'
    return str(val)

print(standardize_picheta_matiere("TRANSPORT DÉCHETS VÉGÉTAUX"))
