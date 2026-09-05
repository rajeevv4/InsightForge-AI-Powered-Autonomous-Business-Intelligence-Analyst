#!/usr/bin/env python3
"""
InsightForge — ETL & Database Seeding Script
============================================
This script loads raw Olist Brazilian E-Commerce CSV files, cleans and transforms
the dataset (including English category translation), creates the PostgreSQL schema,
and bulk inserts records into the InsightForge business database.

Supported raw CSVs in `data/raw/`:
  1. olist_customers_dataset.csv
  2. olist_products_dataset.csv
  3. product_category_name_translation.csv
  4. olist_sellers_dataset.csv
  5. olist_orders_dataset.csv
  6. olist_order_items_dataset.csv
  7. olist_order_payments_dataset.csv
  8. olist_order_reviews_dataset.csv
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Database Connection Info
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "insightforge")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_SCHEMA = os.getenv("DB_SCHEMA", "insightforge")

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
SCHEMA_SQL_PATH = BASE_DIR / "database" / "schema.sql"
VIEWS_SQL_PATH = BASE_DIR / "database" / "views.sql"

os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
os.makedirs(RAW_DATA_DIR, exist_ok=True)


def get_db_engine():
    """Create and return a SQLAlchemy database engine."""
    if DB_PASSWORD:
        db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        db_url = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(db_url, echo=False)


def apply_sql_file(engine, file_path):
    """Execute raw SQL statements from a file."""
    print(f"📄 Applying SQL script: {file_path.name}")
    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    with engine.begin() as connection:
        connection.execute(text(sql_content))
    print(f"✅ Successfully executed {file_path.name}")


def check_raw_files_exist():
    """Verify presence of required CSV files in data/raw/."""
    required_files = [
        "olist_customers_dataset.csv",
        "olist_products_dataset.csv",
        "product_category_name_translation.csv",
        "olist_sellers_dataset.csv",
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_order_reviews_dataset.csv"
    ]
    missing = [f for f in required_files if not (RAW_DATA_DIR / f).exists()]
    return required_files, missing


def clean_customers():
    file_path = RAW_DATA_DIR / "olist_customers_dataset.csv"
    print("🧹 Cleaning customers table...")
    df = pd.read_csv(file_path)
    df = df.rename(columns={
        "customer_zip_code_prefix": "customer_zip_code_prefix",
    })
    df["customer_city"] = df["customer_city"].str.title().str.strip()
    df["customer_state"] = df["customer_state"].str.upper().str.strip()
    df.to_csv(PROCESSED_DATA_DIR / "customers_cleaned.csv", index=False)
    return df


def clean_products():
    file_path = RAW_DATA_DIR / "olist_products_dataset.csv"
    trans_path = RAW_DATA_DIR / "product_category_name_translation.csv"
    print("🧹 Cleaning products table and translating categories...")
    
    df_prod = pd.read_csv(file_path)
    df_trans = pd.read_csv(trans_path)
    
    # Merge translation
    df_merged = pd.merge(df_prod, df_trans, on="product_category_name", how="left")
    
    # Clean string columns and fill nulls
    df_merged["product_category_name_english"] = df_merged["product_category_name_english"].fillna("uncategorized")
    df_merged["product_category_name"] = df_merged["product_category_name"].fillna("outros")
    
    # Integer columns mapping
    int_cols = [
        "product_name_lenght", "product_description_lenght", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"
    ]
    for col in int_cols:
        df_merged[col] = df_merged[col].fillna(0).astype(int)
        
    df_merged = df_merged.rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length"
    })
    
    df_merged.to_csv(PROCESSED_DATA_DIR / "products_cleaned.csv", index=False)
    return df_merged


def clean_sellers():
    file_path = RAW_DATA_DIR / "olist_sellers_dataset.csv"
    print("🧹 Cleaning sellers table...")
    df = pd.read_csv(file_path)
    df["seller_city"] = df["seller_city"].str.title().str.strip()
    df["seller_state"] = df["seller_state"].str.upper().str.strip()
    df.to_csv(PROCESSED_DATA_DIR / "sellers_cleaned.csv", index=False)
    return df


def clean_orders():
    file_path = RAW_DATA_DIR / "olist_orders_dataset.csv"
    print("🧹 Cleaning orders table...")
    df = pd.read_csv(file_path)
    
    ts_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ]
    for col in ts_cols:
        df[col] = pd.to_datetime(df[col], errors='coerce')
        
    df.to_csv(PROCESSED_DATA_DIR / "orders_cleaned.csv", index=False)
    return df


def clean_order_items():
    file_path = RAW_DATA_DIR / "olist_order_items_dataset.csv"
    print("🧹 Cleaning order items table...")
    df = pd.read_csv(file_path)
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors='coerce')
    df["price"] = df["price"].round(2)
    df["freight_value"] = df["freight_value"].round(2)
    df.to_csv(PROCESSED_DATA_DIR / "order_items_cleaned.csv", index=False)
    return df


def clean_order_payments():
    file_path = RAW_DATA_DIR / "olist_order_payments_dataset.csv"
    print("🧹 Cleaning order payments table...")
    df = pd.read_csv(file_path)
    df["payment_sequential"] = df["payment_sequential"].astype(int)
    df["payment_installments"] = df["payment_installments"].astype(int)
    df["payment_value"] = df["payment_value"].round(2)
    df.to_csv(PROCESSED_DATA_DIR / "order_payments_cleaned.csv", index=False)
    return df


def clean_order_reviews():
    file_path = RAW_DATA_DIR / "olist_order_reviews_dataset.csv"
    print("🧹 Cleaning order reviews table...")
    df = pd.read_csv(file_path)
    
    # Deduplicate review_id, order_id PK constraint if any
    df = df.drop_duplicates(subset=["review_id", "order_id"])
    
    df["review_score"] = df["review_score"].fillna(3).astype(int)
    df["review_creation_date"] = pd.to_datetime(df["review_creation_date"], errors='coerce')
    df["review_answer_timestamp"] = pd.to_datetime(df["review_answer_timestamp"], errors='coerce')
    
    df["review_comment_title"] = df["review_comment_title"].fillna("")
    df["review_comment_message"] = df["review_comment_message"].fillna("")
    
    df.to_csv(PROCESSED_DATA_DIR / "order_reviews_cleaned.csv", index=False)
    return df


def load_data_to_postgres(engine):
    """Load cleaned dataframes into PostgreSQL database in relational dependency order."""
    print("\n🚀 Bulk loading transformed tables into PostgreSQL...")
    
    tables_order = [
        ("customers", clean_customers),
        ("products", clean_products),
        ("sellers", clean_sellers),
        ("orders", clean_orders),
        ("order_items", clean_order_items),
        ("order_payments", clean_order_payments),
        ("order_reviews", clean_order_reviews)
    ]
    
    with engine.begin() as conn:
        conn.execute(text(f"SET search_path TO {DB_SCHEMA}, public;"))
        
    for table_name, clean_func in tables_order:
        df = clean_func()
        print(f"📥 Inserting {len(df):,} rows into '{DB_SCHEMA}.{table_name}'...")
        df.to_sql(
            name=table_name,
            con=engine,
            schema=DB_SCHEMA,
            if_exists="append",
            index=False,
            chunksize=5000,
            method="multi"
        )
        print(f"✅ Loaded '{table_name}' successfully.")


def main():
    print("=" * 65)
    print("  INSIGHTFORGE — DATASET ETL & POSTGRESQL SEEDING PIPELINE  ")
    print("=" * 65)
    
    required_files, missing = check_raw_files_exist()
    if missing:
        print("\n⚠️ WARNING: Missing raw CSV files in `data/raw/`:")
        for m in missing:
            print(f"   - {m}")
        print("\nPlease download the Olist E-Commerce dataset CSV files from Kaggle or")
        print(f"place them directly inside: {RAW_DATA_DIR.resolve()}")
        print("\nSupported files:")
        for r in required_files:
            print(f"   • {r}")
        sys.exit(1)
        
    try:
        engine = get_db_engine()
        print(f"\n🔌 Connected to PostgreSQL database '{DB_NAME}' at {DB_HOST}:{DB_PORT}")
        
        # 1. Execute schema creation
        apply_sql_file(engine, SCHEMA_SQL_PATH)
        
        # 2. Load data
        load_data_to_postgres(engine)
        
        # 3. Create views
        apply_sql_file(engine, VIEWS_SQL_PATH)
        
        print("\n🎉 ETL and PostgreSQL Database Seeding Completed Successfully!")
        print("Run `python database/verify_db.py` to inspect database health.")
        
    except Exception as e:
        print(f"\n❌ Pipeline failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
