# -*- coding: utf-8 -*-
"""Load and clean the raw Astram incident CSV."""
import pandas as pd
import numpy as np
from . import config


def load_raw() -> pd.DataFrame:
    """Read the raw CSV with robust encoding handling."""
    df = pd.read_csv(
        config.DATA_RAW,
        dtype=str,                 # read everything as string first; coerce later
        keep_default_na=False,     # we handle NA tokens ourselves
        encoding="utf-8",
        encoding_errors="replace",
    )
    return df


def _normalise_na(df: pd.DataFrame) -> pd.DataFrame:
    """Replace dataset-specific NULL tokens with real NaN."""
    with pd.option_context("future.no_silent_downcasting", True):
        return df.replace(list(config.NA_TOKENS), np.nan).infer_objects(copy=False)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Type-coerce and tidy the raw frame."""
    df = _normalise_na(df.copy())

    # numeric coordinates
    for col in ["latitude", "longitude", "endlatitude", "endlongitude",
                "resolved_at_latitude", "resolved_at_longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            # 0.0 coordinates are placeholders -> treat as missing
            df.loc[df[col] == 0, col] = np.nan

    # timestamps -> timezone-aware datetimes (then drop tz for simplicity)
    for col in config.TIME_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_localize(None)

    # boolean-ish
    if "requires_road_closure" in df.columns:
        df["requires_road_closure"] = (
            df["requires_road_closure"].str.upper().map({"TRUE": True, "FALSE": False})
        )

    # normalise key categoricals to lowercase/stripped
    for col in ["event_type", "event_cause", "status", "priority", "veh_type",
                "corridor", "zone", "junction", "police_station"]:
        if col in df.columns:
            df[col] = df[col].str.strip()

    return df


def load_clean() -> pd.DataFrame:
    """Convenience: raw -> cleaned frame."""
    return clean(load_raw())


if __name__ == "__main__":
    d = load_clean()
    print("rows, cols:", d.shape)
    print("dtypes sample:\n", d[["start_datetime", "latitude", "requires_road_closure"]].dtypes)
