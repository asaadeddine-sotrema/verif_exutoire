import pandas as pd
from modules.verif_dupille import resolve_col
import numpy as np

# Mocking data specifically to trace INT Client from start to finish
df = pd.DataFrame({
    'Num Ticket': ['T1', 'T2', 'T3'],
    'INT Client_T': ['C1_TER', 'C2_TER', np.nan],
    'EXT Client_F': ['C1_FAC', np.nan, 'C3_FAC'],
    '_merge': ['both', 'left_only', 'right_only']
})

print("resolve_col('INT Client')")
print(resolve_col(df, 'INT Client'))
print("resolve_col('EXT Client')")
print(resolve_col(df, 'EXT Client'))

