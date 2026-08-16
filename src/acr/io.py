"""Small helpers for reading and converting analysis outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_forecast_paths_parquet(tables_dir: Path | None = None) -> Path:
    """Return the forecast path parquet, converting from CSV if needed."""
    out = tables_dir or project_root() / "outputs" / "tables"
    parquet_path = out / "forecast_paths.parquet"
    csv_path = out / "forecast_paths.csv"
    if parquet_path.exists():
        return parquet_path
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Need {parquet_path.name} or {csv_path.name} in {out}"
        )
    frame = pd.read_csv(csv_path)
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def main() -> None:
    path = ensure_forecast_paths_parquet()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
