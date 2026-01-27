import pandas as pd
import numpy as np

# Updated function from app.py
def normalize_site_key(txt):
    if pd.isna(txt): return "NAN"
    t = str(txt).upper().strip()
    
    # Mappings spécifiques (Règles métier)
    if "CTC MLV" in t and "GRAND OUEST" in t: return "BUCHELAY" # Règle explicite 
    
    t = t.replace("MLJ", "MANTES JOLIE").replace("MLV", "MANTES VILLE")
    
    # Tokenization et nettoyage (remplace ponctuation par espace)
    for char in ["-", "_", ".", "/"]:
        t = t.replace(char, " ")
        
    words = t.split()
    stopwords = ["DECHETERIE", "DECHETTERIE", "CTC", "SITE", "SUEZ", "RV", "OSIS", "DES", "LES", "DU", "DE", "LA", "LE", "ET", "COMMUNAUTE", "URBAINE"]
    
    # On garde les mots qui NE SONT PAS des stopwords et > 2 lettres
    tokens = sorted([w for w in words if w not in stopwords and len(w) > 2])
    
    if not tokens: return "EMPTY"
    return " ".join(tokens)

def check_client_suez(row):
    int_c = str(row.get('INT Client', '')).upper().strip()
    ext_c = str(row.get('EXT Client', '')).upper().strip()
    
    # 1. Cas trivial
    if not int_c or not ext_c: return "Ingorable"
    if int_c == ext_c: return "OK"
    
    # 2. Utilisation de la clé normalisée partagée
    k1 = normalize_site_key(int_c)
    k2 = normalize_site_key(ext_c)
    
    # Debug print
    print(f"INT: '{int_c}' -> Key: '{k1}'")
    print(f"EXT: '{ext_c}' -> Key: '{k2}'")
    
    if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "Ingorable"
    
    # Intersection des tokens normalisés
    s1 = set(k1.split())
    s2 = set(k2.split())
    if s1.intersection(s2): return "OK"
    
    # 3. Rattrapage GPSO (si fallback)
    if "GPSO" in int_c and "GPS" in ext_c: return "OK"
    
    return "Pb.Clt"

# Test cases
rows = [
    {'INT Client': 'CTC MLV - CTC DU GRAND OUEST', 'EXT Client': 'BUCHELAY'},
    {'INT Client': 'CTC MLV - CTC DU GRAND OUEST', 'EXT Client': 'SUEZ RV BUCHELAY'},
    {'INT Client': 'MANTES LA VILLE', 'EXT Client': 'BUCHELAY'},  # Expect Fail
    {'INT Client': 'CTC MLJ - CTC DU GRAND OUEST', 'EXT Client': 'MANTES JOLIE'}, # Expect OK
    {'INT Client': 'CTC MLV', 'EXT Client': 'MANTES LA VILLE'}, # Existing logic check
]

print("Running Tests...\n")
for i, r in enumerate(rows):
    res = check_client_suez(r)
    print(f"Test {i+1}: {r['INT Client']} vs {r['EXT Client']} => {res}")
    print("-" * 30)
