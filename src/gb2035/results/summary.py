"""Cross-scenario summary table."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ORDER = [
    "uncapped",
    "cap30",
    "cap20",
    "cap10",
    "cap5",
    "cap2",
    "cap0p5",
    "cap5_no_h2",
    "cap5_ee_demand",
    "cap5_tx_expansion",
    "cap5_steel",
    "test",
]


def summarise(results_root: Path) -> pd.DataFrame:
    rows = [pd.read_csv(p) for p in sorted(results_root.glob("*/summary_row.csv"))]
    if not rows:
        return pd.DataFrame(columns=["scenario"])
    df = pd.concat(rows, ignore_index=True)
    rank = {name: i for i, name in enumerate(ORDER)}
    df["_rank"] = df["scenario"].map(lambda s: rank.get(s, len(ORDER)))
    return df.sort_values(["_rank", "scenario"]).drop(columns="_rank").reset_index(drop=True)


def write_summary(results_root: Path) -> Path:
    path = results_root / "summary.csv"
    summarise(results_root).to_csv(path, index=False, float_format="%.6g")
    return path
