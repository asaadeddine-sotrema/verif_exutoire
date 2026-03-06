import pandas as pd
import unicodedata

def normaliser_matiere_picheta_valoseine(m):
    if not m or pd.isna(m): return ""
    import unicodedata
    s = str(m).upper().strip()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    if "GRAVATS" in s: return "GRAVATS"
    if "DECHETS VERTS" in s or "VERTS" in s: return "DECHETS VERTS"
    if "BOIS" in s: return "BOIS"
    if "ENCOMBRANTS" in s: return "DIB"
    if "TOUT VENANT" in s: return "TOUT VENANT"
    return s

test_cases = [
    "DÉCOM - GRAVATS RECYCLABLES",
    "GRAVATS",
    "B.A. BOIS NON TRAITÉ",
    "BOIS",
    "TRANSPORT DÉCHETS VÉGÉTAUX",
    "TRANSPORT FERRAILLES",
    "TRANSPORT CARTONS",
    "TRANSPORT PLÂTRE",
    "TRANSPORT DVE DIMANCHE & JOU"
]

for t in test_cases:
    print(f"{t} -> {normaliser_matiere_picheta_valoseine(t)}")
