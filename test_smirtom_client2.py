import pandas as pd
import numpy as np
from app import resolve_col

# Mock final DataFrame after merge
final = pd.DataFrame({
    'Num Ticket': ['T1', 'T2'],
    'EXT Client_F': ['Code Adr 1', np.nan]
})

print("Simulation:")
print(final.get('EXT Client_F').combine_first(final.get('Client_F', pd.Series([np.nan]*len(final)))).fillna("DECHETERIE PICHETA SMIRTOM").tolist())
