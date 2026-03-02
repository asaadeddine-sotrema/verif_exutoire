import pandas as pd
from datetime import time, datetime

def parse_tps_travail(val):
    print(f"Type: {type(val)}, Value: {repr(val)}")
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    if isinstance(val, datetime): return val.hour + val.minute / 60.0
    if isinstance(val, time): return val.hour + val.minute / 60.0
    if isinstance(val, str):
        try:
            t = datetime.strptime(val, "%H:%M:%S").time()
            return t.hour + t.minute / 60.0
        except ValueError:
            try:
                t = datetime.strptime(val, "%H:%M").time()
                return t.hour + t.minute / 60.0
            except ValueError:
                pass
    return 0.0

# Simulate what Excel might give us for TpsTravail
dummy_data = pd.DataFrame({"TpsTravail": ["08:00", "08:00:00", 8.0, 8, time(8, 0), pd.Timestamp("2023-01-01 08:30:00")]})

dummy_data['Duree'] = dummy_data['TpsTravail'].apply(parse_tps_travail)
print(dummy_data)
