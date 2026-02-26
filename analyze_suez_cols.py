
import pandas as pd

f_dech = '/home/amine/projects/Contrôle DECHETTERIE du 01 au 15-02-2026.xlsx'

print("--- ANALYZING COLUMNS ---")
try:
    df = pd.read_excel(f_dech, header=None, dtype=str)
    print(f"Shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    print("First 10 rows values:")
    print(df.head(10).to_string())
    
    # Check for keywords in first few rows to find where logic fails
    
        
except Exception as e:
    print(f"Error: {e}")
