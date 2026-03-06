import pandas as pd
import numpy as np
from modules.verif_dupille import resolve_multi as resolve_multi_dupille
from modules.verif_valene import verif_client as verif_client_valene

def test_resolve_multi_issue():
    print("Testing resolve_multi with empty strings...")
    # Simulate the issue where a column is already populated with ''
    df = pd.DataFrame({
        'INT Client': ['', ''], # Prematurely converted to '' in charger_dupille
        'INT Client_T': ['CLIENT A', 'CLIENT B']
    })
    
    # Current behavior check
    res = resolve_multi_dupille(df, ["INT Client"])
    print(f"Result with current resolve_multi: {res.tolist()}")
    # If it returns [NaN, NaN], that's the bug!
    
def test_valene_client_match():
    print("\nTesting Valene GPSEO / GRAND PARIS SEINE ET OISE match...")
    # Case 1: GPSEO vs CU GRAND PARIS SEINE ET OISE (should be OK)
    row1 = {'INT Client': 'GPSEO', 'EXT Client': 'CU GRAND PARIS SEINE ET OISE', 'Activité': 'PAP'}
    # Case 2: GPSEO vs GRAND PARIS SEINE ET OISE (reported as Pb.Clt)
    row2 = {'INT Client': 'GPSEO', 'EXT Client': 'GRAND PARIS SEINE ET OISE', 'Activité': 'PAP'}
    
    print(f"Row 1 (CU): {verif_client_valene(row1)}")
    print(f"Row 2 (No CU): {verif_client_valene(row2)}")

if __name__ == "__main__":
    test_resolve_multi_issue()
    test_valene_client_match()
