import pandas as pd
import unicodedata

def standardize_picheta_matiere(val):
    if pd.isna(val) or str(val).strip() == "":
        return val
    v = str(val).lower()
    
    # Let's remove accents for robust matching
    v = unicodedata.normalize('NFKD', v).encode('ASCII', 'ignore').decode('utf-8')
    
    if 'vegetau' in v or 'dve' in v:
        return 'DEPOT VEGETAUX TVA10 - BPU 4.2'
    if 'carton' in v:
        return 'DEPOT PAPIER CARTON TVA0 - BPU 4.7'
    if 'gravat' in v:
        return 'DEPOT GRAVAT CHANTIER TVA10 - BPU 4.1'
    if 'platre' in v:
        return 'DEPOT PLATRE TVA5.5 - BPU 4.8'
    if 'ferraille' in v:
        return 'DEPOT FERRAILLE TVA0 - BPU 4.6' # Corrected based on image
    return str(val)

test_cases = [
    "TRANSPORT DÉCHETS VÉGÉTAUX",
    "TRANSPORT FERRAILLES",
    "TRANSPORT CARTONS",
    "TRANSPORT PLÂTRE",
    "GRAVATS",
    "TRANSPORT DVE DIMANCHE & JOU",
    "TRANSPORT CARTONS DIMANCHE"
]

for t in test_cases:
    print(f"{t} -> {standardize_picheta_matiere(t)}")
