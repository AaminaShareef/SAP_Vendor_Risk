"""
SAP Vendor Risk Analysis - ML Engine
Reads BSIK_Open_Items, LFA1_Vendor_Master_General, LFB1_Vendor_Master_CompCode
and performs vendor aging analysis, risk scoring, K-Means clustering, and
Random Forest risk prediction.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings("ignore")


def run_vendor_risk_analysis(bsik_path: str, lfa1_path: str, lfb1_path: str) -> dict:
    """
    Main entry point for vendor risk analysis.
    Returns a dict of results ready to serialize to JSON.
    """
    # ── 1. Load data ────────────────────────────────────────────────────────
    bsik = _load_bsik(bsik_path)
    lfa1 = _load_lfa1(lfa1_path)
    lfb1 = _load_lfb1(lfb1_path)

    # ── 2. Aging & overdue calculation ──────────────────────────────────────
    bsik = _compute_aging(bsik)

    # ── 3. Aggregate per vendor ──────────────────────────────────────────────
    vendor_agg = _aggregate_vendor(bsik)

    # ── 4. Merge master data ─────────────────────────────────────────────────
    vendor_df = _merge_master(vendor_agg, lfa1, lfb1)

    # ── 5. Risk scoring ──────────────────────────────────────────────────────
    vendor_df = _compute_risk_score(vendor_df)

    # ── 6. K-Means clustering ────────────────────────────────────────────────
    vendor_df = _kmeans_cluster(vendor_df)

    # ── 7. Random Forest prediction ──────────────────────────────────────────
    vendor_df = _random_forest_predict(vendor_df)

    # ── 8. Build result payload ──────────────────────────────────────────────
    return _build_result(vendor_df, bsik)


# ── Loaders ──────────────────────────────────────────────────────────────────

def _load_bsik(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]

    # Flexible column mapping
    col_map = {
        "LIFNR": ["LIFNR", "VENDOR", "VENDOR_ID", "VENDOR ID"],
        "BLDAT": ["BLDAT", "DOCUMENT_DATE", "DOC_DATE", "POSTING_DATE", "BUDAT"],
        "DMBTR": ["DMBTR", "AMOUNT", "AMOUNT_LC", "LC_AMOUNT", "WRBTR"],
        "ZFBDT": ["ZFBDT", "DUE_DATE", "NET_DUE_DATE", "BASELINE_DATE"],
        "ZBD1T": ["ZBD1T", "PAYMENT_TERMS", "PAYMENT_DAYS", "CASH_DISC_DAYS"],
    }
    df = _remap_columns(df, col_map)

    # Parse dates
    for date_col in ["BLDAT", "ZFBDT"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)

    # Ensure numeric amount
    if "DMBTR" in df.columns:
        df["DMBTR"] = pd.to_numeric(df["DMBTR"], errors="coerce").fillna(0).abs()
    else:
        df["DMBTR"] = 0.0

    # Fill missing LIFNR
    if "LIFNR" not in df.columns:
        df["LIFNR"] = "UNKNOWN"

    return df


def _load_lfa1(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]
    col_map = {
        "LIFNR": ["LIFNR", "VENDOR", "VENDOR_ID"],
        "NAME1": ["NAME1", "VENDOR_NAME", "NAME", "VENDOR NAME"],
        "LAND1": ["LAND1", "COUNTRY", "COUNTRY_CODE"],
        "ORT01": ["ORT01", "CITY", "CITY_NAME"],
        "KTOKK": ["KTOKK", "ACCOUNT_GROUP", "ACCT_GRP"],
    }
    return _remap_columns(df, col_map)


def _load_lfb1(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]
    col_map = {
        "LIFNR": ["LIFNR", "VENDOR", "VENDOR_ID"],
        "BUKRS": ["BUKRS", "COMPANY_CODE", "COMP_CODE"],
        "AKONT": ["AKONT", "RECON_ACCOUNT", "RECONCILIATION_ACCOUNT"],
        "ZTERM": ["ZTERM", "PAYMENT_TERMS", "PAY_TERMS"],
    }
    return _remap_columns(df, col_map)


def _remap_columns(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Rename first matching alias → canonical name."""
    rename = {}
    for canonical, aliases in col_map.items():
        if canonical in df.columns:
            continue
        for alias in aliases:
            if alias in df.columns:
                rename[alias] = canonical
                break
    return df.rename(columns=rename)


# ── Processing ────────────────────────────────────────────────────────────────

def _compute_aging(df: pd.DataFrame) -> pd.DataFrame:
    today = datetime.today()
    # Use ZFBDT (due date) if available, else BLDAT
    date_col = "ZFBDT" if "ZFBDT" in df.columns else "BLDAT"
    if date_col in df.columns:
        df["DAYS_OVERDUE"] = (today - df[date_col]).dt.days.clip(lower=0)
    else:
        df["DAYS_OVERDUE"] = 0

    # Aging bucket
    bins = [-1, 30, 60, 90, 120, float("inf")]
    labels = ["0-30", "31-60", "61-90", "91-120", "120+"]
    df["AGING_BUCKET"] = pd.cut(df["DAYS_OVERDUE"], bins=bins, labels=labels)
    return df


def _aggregate_vendor(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby("LIFNR").agg(
        TOTAL_INVOICES=("DMBTR", "count"),
        TOTAL_OVERDUE_AMOUNT=("DMBTR", "sum"),
        MAX_DAYS_OVERDUE=("DAYS_OVERDUE", "max"),
        AVG_DAYS_OVERDUE=("DAYS_OVERDUE", "mean"),
    ).reset_index()

    # Aging bucket counts
    if "AGING_BUCKET" in df.columns:
        bucket_counts = (
            df.groupby(["LIFNR", "AGING_BUCKET"], observed=True)
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        bucket_counts.columns.name = None
        for b in ["0-30", "31-60", "61-90", "91-120", "120+"]:
            if b not in bucket_counts.columns:
                bucket_counts[b] = 0
        agg = agg.merge(bucket_counts, on="LIFNR", how="left")

    return agg


def _merge_master(agg: pd.DataFrame, lfa1: pd.DataFrame, lfb1: pd.DataFrame) -> pd.DataFrame:
    # Keep only needed cols from master
    lfa1_cols = ["LIFNR"] + [c for c in ["NAME1", "LAND1", "ORT01", "KTOKK"] if c in lfa1.columns]
    lfb1_cols = ["LIFNR"] + [c for c in ["BUKRS", "ZTERM"] if c in lfb1.columns]

    df = agg.merge(lfa1[lfa1_cols].drop_duplicates("LIFNR"), on="LIFNR", how="left")
    df = df.merge(lfb1[lfb1_cols].drop_duplicates("LIFNR"), on="LIFNR", how="left")

    df["NAME1"] = df["NAME1"].fillna("Unknown Vendor") if "NAME1" in df.columns else "Unknown Vendor"
    return df


def _compute_risk_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Risk Score (0-100) composite:
      50% → overdue amount (normalised)
      30% → max days overdue (normalised)
      20% → invoice count (normalised)
    """
    def _norm(s: pd.Series) -> pd.Series:
        mn, mx = s.min(), s.max()
        return (s - mn) / (mx - mn + 1e-9)

    score = (
        0.50 * _norm(df["TOTAL_OVERDUE_AMOUNT"]) +
        0.30 * _norm(df["MAX_DAYS_OVERDUE"]) +
        0.20 * _norm(df["TOTAL_INVOICES"])
    ) * 100

    df["RISK_SCORE"] = score.round(2)
    return df


def _kmeans_cluster(df: pd.DataFrame) -> pd.DataFrame:
    features = ["TOTAL_OVERDUE_AMOUNT", "MAX_DAYS_OVERDUE", "TOTAL_INVOICES", "RISK_SCORE"]
    X = df[features].fillna(0)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(4, len(df))
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df["CLUSTER"] = km.fit_predict(X_scaled)
    return df


def _random_forest_predict(df: pd.DataFrame) -> pd.DataFrame:
    """
    Label via risk score thresholds → train RF → predict on full dataset.
    Labels: Low (<25), Medium (25-50), High (50-75), Critical (>75)
    """
    def score_to_label(s):
        if s < 25:
            return "Low"
        elif s < 50:
            return "Medium"
        elif s < 75:
            return "High"
        else:
            return "Critical"

    df["TRUE_LABEL"] = df["RISK_SCORE"].apply(score_to_label)

    features = ["TOTAL_OVERDUE_AMOUNT", "MAX_DAYS_OVERDUE", "TOTAL_INVOICES",
                "AVG_DAYS_OVERDUE", "RISK_SCORE", "CLUSTER"]
    X = df[features].fillna(0)
    y = df["TRUE_LABEL"]

    if len(df) >= 10:
        X_tr, X_te, y_tr, _ = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    else:
        X_tr, y_tr = X, y

    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_tr, y_tr)
    df["PREDICTED_RISK"] = rf.predict(X)
    return df


# ── Result builder ────────────────────────────────────────────────────────────

def _build_result(vendor_df: pd.DataFrame, bsik: pd.DataFrame) -> dict:
    risk_order = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}

    # KPI
    total_vendors = len(vendor_df)
    total_overdue = float(vendor_df["TOTAL_OVERDUE_AMOUNT"].sum())
    high_risk = int((vendor_df["PREDICTED_RISK"] == "High").sum())
    critical = int((vendor_df["PREDICTED_RISK"] == "Critical").sum())

    # Aging buckets (aggregate across all items)
    aging_buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "91-120": 0, "120+": 0}
    if "AGING_BUCKET" in bsik.columns:
        bc = bsik.groupby("AGING_BUCKET", observed=True)["DMBTR"].sum()
        for k in aging_buckets:
            aging_buckets[k] = float(bc.get(k, 0))

    # Risk distribution
    risk_dist = vendor_df["PREDICTED_RISK"].value_counts().to_dict()
    for lvl in ["Low", "Medium", "High", "Critical"]:
        risk_dist.setdefault(lvl, 0)

    # Top 10 risky vendors
    top10 = (
        vendor_df.nlargest(10, "TOTAL_OVERDUE_AMOUNT")
        [["LIFNR", "NAME1", "TOTAL_OVERDUE_AMOUNT", "RISK_SCORE", "PREDICTED_RISK"]]
        if "NAME1" in vendor_df.columns
        else vendor_df.nlargest(10, "TOTAL_OVERDUE_AMOUNT")
        [["LIFNR", "TOTAL_OVERDUE_AMOUNT", "RISK_SCORE", "PREDICTED_RISK"]]
    )
    top10 = top10.rename(columns={"LIFNR": "vendor_id", "NAME1": "vendor_name",
                                   "TOTAL_OVERDUE_AMOUNT": "overdue_amount",
                                   "RISK_SCORE": "risk_score",
                                   "PREDICTED_RISK": "predicted_risk"})
    if "vendor_name" not in top10.columns:
        top10["vendor_name"] = top10["vendor_id"]
    top10["overdue_amount"] = top10["overdue_amount"].round(2)

    # Scatter data (risk score vs overdue amount)
    scatter = vendor_df[["LIFNR", "RISK_SCORE", "TOTAL_OVERDUE_AMOUNT", "PREDICTED_RISK"]].copy()
    if "NAME1" in vendor_df.columns:
        scatter["NAME1"] = vendor_df["NAME1"]
    scatter = scatter.rename(columns={"LIFNR": "vendor_id", "NAME1": "vendor_name",
                                       "RISK_SCORE": "risk_score",
                                       "TOTAL_OVERDUE_AMOUNT": "overdue_amount",
                                       "PREDICTED_RISK": "predicted_risk"})
    if "vendor_name" not in scatter.columns:
        scatter["vendor_name"] = scatter["vendor_id"]
    scatter["overdue_amount"] = scatter["overdue_amount"].round(2)

    # Full vendor table
    table_cols = {
        "LIFNR": "vendor_id",
        "NAME1": "vendor_name",
        "TOTAL_OVERDUE_AMOUNT": "overdue_amount",
        "RISK_SCORE": "risk_score",
        "PREDICTED_RISK": "predicted_risk",
        "TOTAL_INVOICES": "total_invoices",
        "MAX_DAYS_OVERDUE": "max_days_overdue",
        "AVG_DAYS_OVERDUE": "avg_days_overdue",
    }
    available = {k: v for k, v in table_cols.items() if k in vendor_df.columns}
    table = vendor_df[list(available.keys())].rename(columns=available).copy()
    if "vendor_name" not in table.columns:
        table["vendor_name"] = table["vendor_id"]
    table["overdue_amount"] = table["overdue_amount"].round(2)
    table["risk_score"] = table["risk_score"].round(2)
    table = table.sort_values("overdue_amount", ascending=False)

    return {
        "kpi": {
            "total_vendors": total_vendors,
            "total_overdue": round(total_overdue, 2),
            "high_risk": high_risk,
            "critical": critical,
        },
        "aging_buckets": aging_buckets,
        "risk_distribution": risk_dist,
        "top10": top10.to_dict(orient="records"),
        "scatter": scatter.to_dict(orient="records"),
        "vendors": table.to_dict(orient="records"),
    }
