import pandas as pd
import pm4py

raw_log_path = "data/raw/BPI_Challenge_2012.xes"
output_parquet_path = "data/interim/bpic2012.parquet"

log = pm4py.read_xes(raw_log_path)
df = pm4py.convert_to_dataframe(log)

df = df.rename(
    columns={
        "case:concept:name": "case_id",
        "concept:name": "activity",
        "time:timestamp": "timestamp",
        "org:resource": "resource",
    }
)

df["case_start"] = df.groupby("case_id")["timestamp"].transform("min")

df = df.sort_values(by=["case_start", "case_id", "timestamp"]).reset_index(
    drop=True
)

df = df.drop(columns=["case_start"])
df.to_parquet(output_parquet_path, index=False)

print(
    f"Successfully processed {len(df):,} events and saved to {output_parquet_path}."
)