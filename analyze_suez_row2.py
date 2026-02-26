
import pandas as pd

f_dech = '/home/amine/projects/Contrôle DECHETTERIE du 01 au 15-02-2026.xlsx'

print("--- ANALYZING ROW 2 ---")
try:
    df = pd.read_excel(f_dech, header=None, nrows=5)
    print("Row 2 values:")
    print(df.iloc[2].tolist())
    
    row_str = str(df.iloc[2].values).lower()
    print(f"Row 2 string: {row_str}")
    
    keywords = ['ticket', 'tp manuel', 'bon', 'vidage', 'n°', 'date', 'poids', 'quantité', 'produit', 'immat', 'client', 'chantier']
    score = 0
    for k in keywords:
        if k in row_str: 
            print(f"Found keyword: {k}")
            score += 1
    print(f"Score: {score}")

except Exception as e:
    print(f"Error: {e}")
