"""
SAP Vendor Risk Analysis - ML Engine
Uses K-Means clustering to classify vendors into risk groups
and returns top risky vendors with full analytics output.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")


def run_vendor_risk_analysis(bsik_path: str, lfa1_path: str, lfb1_path: str) -> dict:

    # 1 Load data
    bsik = _load_bsik(bsik_path)
    lfa1 = _load_lfa1(lfa1_path)
    lfb1 = _load_lfb1(lfb1_path)

    # 2 Aging analysis
    bsik = _compute_aging(bsik)

    # 3 Vendor aggregation
    vendor_agg = _aggregate_vendor(bsik)

    # 4 Merge vendor master data
    vendor_df = _merge_master(vendor_agg, lfa1, lfb1)

    # 5 Compute risk score
    vendor_df = _compute_risk_score(vendor_df)

    # 6 ML clustering
    vendor_df = _kmeans_risk_clustering(vendor_df)

    # 7 Build result output
    return _build_result(vendor_df, bsik)


# --------------------------------------------------
# DATA LOADERS
# --------------------------------------------------

def _load_bsik(path):

    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]

    col_map = {
        "LIFNR": ["LIFNR", "VENDOR", "VENDOR_ID"],
        "BLDAT": ["BLDAT", "DOCUMENT_DATE", "POSTING_DATE"],
        "DMBTR": ["DMBTR", "AMOUNT", "WRBTR"],
        "ZFBDT": ["ZFBDT", "DUE_DATE", "BASELINE_DATE"]
    }

    df = _remap_columns(df, col_map)

    for col in ["BLDAT", "ZFBDT"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    df["DMBTR"] = pd.to_numeric(df["DMBTR"], errors="coerce").fillna(0).abs()

    return df


def _load_lfa1(path):

    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]

    col_map = {
        "LIFNR": ["LIFNR", "VENDOR"],
        "NAME1": ["NAME1", "VENDOR_NAME"],
        "LAND1": ["LAND1", "COUNTRY"],
        "ORT01": ["ORT01", "CITY"]
    }

    return _remap_columns(df, col_map)


def _load_lfb1(path):

    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]

    col_map = {
        "LIFNR": ["LIFNR", "VENDOR"],
        "BUKRS": ["BUKRS", "COMPANY_CODE"],
        "ZTERM": ["ZTERM", "PAYMENT_TERMS"]
    }

    return _remap_columns(df, col_map)


def _remap_columns(df, col_map):

    rename = {}

    for canonical, aliases in col_map.items():
        if canonical in df.columns:
            continue

        for alias in aliases:
            if alias in df.columns:
                rename[alias] = canonical
                break

    return df.rename(columns=rename)


# --------------------------------------------------
# AGING ANALYSIS
# --------------------------------------------------

def _compute_aging(df):

    today = datetime.today()

    date_col = "ZFBDT" if "ZFBDT" in df.columns else "BLDAT"

    df["DAYS_OVERDUE"] = (today - df[date_col]).dt.days.clip(lower=0)

    bins = [-1,30,60,90,120,float("inf")]
    labels = ["0-30","31-60","61-90","91-120","120+"]

    df["AGING_BUCKET"] = pd.cut(df["DAYS_OVERDUE"], bins=bins, labels=labels)

    return df


# --------------------------------------------------
# VENDOR AGGREGATION
# --------------------------------------------------

def _aggregate_vendor(df):

    agg = df.groupby("LIFNR").agg(

        TOTAL_INVOICES=("DMBTR","count"),
        TOTAL_OVERDUE_AMOUNT=("DMBTR","sum"),
        MAX_DAYS_OVERDUE=("DAYS_OVERDUE","max"),
        AVG_DAYS_OVERDUE=("DAYS_OVERDUE","mean")

    ).reset_index()

    return agg


# --------------------------------------------------
# MERGE MASTER DATA
# --------------------------------------------------

def _merge_master(agg,lfa1,lfb1):

    lfa1_cols = ["LIFNR"] + [c for c in ["NAME1","LAND1","ORT01"] if c in lfa1.columns]
    lfb1_cols = ["LIFNR"] + [c for c in ["BUKRS","ZTERM"] if c in lfb1.columns]

    df = agg.merge(lfa1[lfa1_cols].drop_duplicates("LIFNR"), on="LIFNR", how="left")
    df = df.merge(lfb1[lfb1_cols].drop_duplicates("LIFNR"), on="LIFNR", how="left")

    df["NAME1"] = df["NAME1"].fillna("Unknown Vendor")

    return df


# --------------------------------------------------
# RISK SCORE
# --------------------------------------------------

def _compute_risk_score(df):

    def normalize(x):
        return (x - x.min()) / (x.max() - x.min() + 1e-9)

    df["RISK_SCORE"] = (
        0.5 * normalize(df["TOTAL_OVERDUE_AMOUNT"]) +
        0.3 * normalize(df["MAX_DAYS_OVERDUE"]) +
        0.2 * normalize(df["TOTAL_INVOICES"])
    ) * 100

    df["RISK_SCORE"] = df["RISK_SCORE"].round(2)

    return df


# --------------------------------------------------
# KMEANS ML CLASSIFICATION
# --------------------------------------------------

def _kmeans_risk_clustering(df):

    features = [
        "TOTAL_OVERDUE_AMOUNT",
        "MAX_DAYS_OVERDUE",
        "TOTAL_INVOICES",
        "RISK_SCORE"
    ]

    X = df[features].fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)

    df["CLUSTER"] = kmeans.fit_predict(X_scaled)

    # Map clusters to risk levels based on avg risk score
    cluster_order = (
        df.groupby("CLUSTER")["RISK_SCORE"]
        .mean()
        .sort_values()
        .index
        .tolist()
    )

    risk_map = {
        cluster_order[0]: "Low",
        cluster_order[1]: "Medium",
        cluster_order[2]: "High",
        cluster_order[3]: "Critical"
    }

    df["RISK_LEVEL"] = df["CLUSTER"].map(risk_map)

    return df


# --------------------------------------------------
# RESULT OUTPUT
# --------------------------------------------------

def _build_result(vendor_df,bsik):

    total_vendors = len(vendor_df)
    total_overdue = float(vendor_df["TOTAL_OVERDUE_AMOUNT"].sum())

    high_risk = int((vendor_df["RISK_LEVEL"]=="High").sum())
    critical = int((vendor_df["RISK_LEVEL"]=="Critical").sum())

    # Aging bucket distribution
    aging = bsik.groupby("AGING_BUCKET")["DMBTR"].sum().to_dict()

    for b in ["0-30","31-60","61-90","91-120","120+"]:
        aging.setdefault(b,0)

    # Risk distribution
    risk_dist = vendor_df["RISK_LEVEL"].value_counts().to_dict()

    for r in ["Low","Medium","High","Critical"]:
        risk_dist.setdefault(r,0)

    # Top 10 risky vendors
    top10 = vendor_df.nlargest(10,"RISK_SCORE")[[
        "LIFNR",
        "NAME1",
        "TOTAL_OVERDUE_AMOUNT",
        "RISK_SCORE",
        "RISK_LEVEL"
    ]]

    top10 = top10.rename(columns={
        "LIFNR":"vendor_id",
        "NAME1":"vendor_name",
        "TOTAL_OVERDUE_AMOUNT":"overdue_amount",
        "RISK_SCORE":"risk_score",
        "RISK_LEVEL":"risk_level"
    })

    # Scatter data
    scatter = vendor_df.rename(columns={
        "LIFNR":"vendor_id",
        "NAME1":"vendor_name",
        "TOTAL_OVERDUE_AMOUNT":"overdue_amount",
        "RISK_SCORE":"risk_score",
        "RISK_LEVEL":"risk_level"
    })[["vendor_id","vendor_name","overdue_amount","risk_score","risk_level"]]

    # Full table
    table = scatter.sort_values("risk_score",ascending=False)

    return {

        "kpi":{

            "total_vendors": total_vendors,
            "total_overdue": round(total_overdue,2),
            "high_risk": high_risk,
            "critical": critical

        },

        "aging_buckets": aging,

        "risk_distribution": risk_dist,

        "top10": top10.to_dict(orient="records"),

        "scatter": scatter.to_dict(orient="records"),

        "vendors": table.to_dict(orient="records")

    }