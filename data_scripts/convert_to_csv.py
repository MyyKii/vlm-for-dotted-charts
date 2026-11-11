import os
import pandas as pd
import pm4py

RAW_FILE = "data/raw/BPI_Challenge_2012.xes"
OUTPUT_CSV = "data/interim/bpic2012.csv"

os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

print("Reading XES ...")
log = pm4py.read_xes(RAW_FILE)
df = pm4py.convert_to_dataframe(log)

df = df.rename(columns={
    'case:concept:name': 'case_id',
    'concept:name': 'activity',
    'time:timestamp': 'timestamp'
})

print(f"Save {len(df)} vents as CSV...")
df.to_csv(OUTPUT_CSV, index=False)
print(f"Successfully saved: {OUTPUT_CSV}")