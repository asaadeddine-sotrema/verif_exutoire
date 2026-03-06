import pandas as pd
import numpy as np
from modules.verif_dupille import resolve_multi as resolve_multi_dupille

def test_dupille_fix():
    print("--- Testing Dupille INT Client Fix ---")
    df = pd.DataFrame({
        'INT Client': ['', ''], # The bug!
        'INT Client_T': ['CLIENT TERRAIN', 'CLIENT TERRAIN 2']
    })
    res = resolve_multi_dupille(df, ["INT Client"])
    print(f"Resolved Clients: {res.tolist()}")
    if res.iloc[0] == 'CLIENT TERRAIN':
        print("✅ Dupille fix successful!")
    else:
        print("❌ Dupille fix failed!")

def test_valene_matching_and_display():
    print("\n--- Testing Valene Matching and Display ---")
    # We can't import the internal functions easily without mocking a lot, 
    # but we can check if the code still compiles and runs a minimal process.
    from modules.verif_valene import process_valene
    import io

    # Mocking files
    f_pap = io.BytesIO()
    df_ter = pd.DataFrame({
        'Num Ticket': ['T001', 'T002'],
        'Poids net': [1000, 2000],
        'Date': ['01/01/2026', '01/01/2026'],
        'Matière': ['DIB', 'BOIS'],
        'Client': ['GPSEO', 'OTHER']
    })
    with pd.ExcelWriter(f_pap) as writer:
        df_ter.to_excel(writer, index=False)
    f_pap.seek(0)

    f_exp = io.BytesIO()
    df_ref = pd.DataFrame({
        'N° de pesée': ['T001'],
        'Poids net': [1.0],
        'Date': ['01/01/2026'],
        'Matière réalisée': ['DIB'],
        'Client': ['GRAND PARIS SEINE ET OISE']
    })
    # Valene expects header at row 8
    df_ref_full = pd.DataFrame([[]]*8 + [df_ref.columns.tolist()] + df_ref.values.tolist())
    with pd.ExcelWriter(f_exp) as writer:
        df_ref_full.to_excel(writer, index=False, header=False)
    f_exp.seek(0)

    try:
        final = process_valene(f_pap, None, None, f_exp)
        print(f"Processed {len(final)} rows")
        
        # Check GPSEO match
        row_matched = final[final['Num Ticket'] == 'T001'].iloc[0]
        print(f"Ticket T001 (GPSEO vs GRAND PARIS): {row_matched['Verif_Client']}")
        
        # Check Orphan display
        row_orphan = final[final['Num Ticket'] == 'T002'].iloc[0]
        print(f"Ticket T002 (Orphan): Client={row_orphan['INT Client']}, Matiere={row_orphan['Matiere_T']}")
        
        if row_matched['Verif_Client'] == 'OK' and row_orphan['INT Client'] == 'OTHER':
            print("✅ Valene fix successful!")
        else:
            print("❌ Valene fix failed!")
            
    except Exception as e:
        print(f"❌ Error during Valene test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_dupille_fix()
    test_valene_matching_and_display()
