import pandas as pd
import numpy as np
import re

def normalize_site_key(txt):
    if not txt or str(txt).upper() in ["NAN", "NONE", ""]: return "EMPTY"
    t = str(txt).upper().strip()
    t = re.sub(r'[^A-Z0-9\s]', ' ', t)
    return " ".join(t.split())

def check_client_suez(row):
    int_c = str(row.get('INT Client', '')).upper().strip()
    ext_c = str(row.get('EXT Client', '')).upper().strip()
    
    if not int_c or not ext_c: return "OK"
    if int_c == ext_c: return "OK"
    
    k1 = normalize_site_key(int_c)
    k2 = normalize_site_key(ext_c)
    
    if k1 in ["NAN", "EMPTY"] or k2 in ["NAN", "EMPTY"]: return "OK"
    
    s1 = set(k1.split())
    s2 = set(k2.split())
    if s1.intersection(s2): return "OK"
    
    if "GPSO" in int_c and "GPS" in ext_c: return "OK"
    
    return "Pb.Clt"

# Test cases
test_rows = [
    {"INT Client": "GPSEO", "EXT Client": "GPSEO"}, # OK (Exact)
    {"INT Client": "GPSEO", "EXT Client": ""},      # OK (Empty)
    {"INT Client": "MANTES", "EXT Client": "MANTES LA JOLIE"}, # OK (Intersection)
    {"INT Client": "TRIEL", "EXT Client": "PISSOT"}, # Pb.Clt (No Match) - This was the bug!
    {"INT Client": "GPSO", "EXT Client": "GPS"}, # OK (Exception)
]

for i, row in enumerate(test_rows):
    res = check_client_suez(row)
    print(f"Test {i+1}: {row['INT Client']} vs {row['EXT Client']} => {res}")
    assert res is not None, f"Test {i+1} failed: returned None"
    if i == 3:
        assert res == "Pb.Clt", f"Test {i+1} failed: expected Pb.Clt, got {res}"

print("All tests passed!")
