import matplotlib.pyplot as plt
import pandas as pd


df = pd.read_parquet("data/interim/bpic2012.parquet")

first_500_cases = df["case_id"].unique()[:500] # takes first 500 cases (my parquet file is already sorted by case_start, case_id, timestamp)
df_sub = df[df["case_id"].isin(first_500_cases)].copy()

case_mapping = {
    case_id: idx for idx, case_id in enumerate(df_sub["case_id"].unique())
}
df_sub["y_index"] = df_sub["case_id"].map(case_mapping)


fig, ax = plt.subplots(figsize=(12, 6), dpi=150)


for activity, group in df_sub.groupby("activity"):
    ax.scatter(
        group["timestamp"],
        group["y_index"],
        label=activity,
        s=4,  # sized of dots. If we have many events, we can reduce the size to avoid clutter
        alpha=0.7,  
    )

ax.set_title("Dotted Chart - BPI Challenge 2012 (First 500 Cases)")
ax.set_xlabel("Timestamp")
ax.set_ylabel("Cases (Sorted by Arrival Time)")

ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", markerscale=3, fontsize=8)
plt.tight_layout()

plt.savefig("test_dotted_chart.png")
print("Saved as 'test_dotted_chart.png'.")