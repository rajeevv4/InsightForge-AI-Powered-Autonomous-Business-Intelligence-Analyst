#!/usr/bin/env python3
"""
InsightForge — Generate Sample Datasets for Testing & Demonstration
===================================================================
Creates 3 test datasets in data/samples/:
1. retail_orders.csv & retail_customers.csv (relational pairs with FK)
2. student_marks.xlsx (Excel format)
3. bike_sharing_messy.tsv (messy headers, ambiguous dates, constant columns)
"""

import os
from pathlib import Path
import pandas as pd

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def generate_sample_datasets():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Creating sample datasets in {SAMPLE_DIR}...")

    # 1. Retail Customers (CSV)
    customers_data = [
        {"customer_id": f"CUST_{i:04d}", "customer_name": f"Customer {i}", "customer_city": ["São Paulo", "Rio de Janeiro", "Curitiba", "Belo Horizonte"][i % 4], "signup_date": f"2023-0{1 + (i % 9):02d}-15", "is_vip": i % 3 == 0}
        for i in range(1, 101)
    ]
    df_customers = pd.DataFrame(customers_data)
    customers_csv = SAMPLE_DIR / "retail_customers.csv"
    df_customers.to_csv(customers_csv, index=False)
    print(f"✅ Generated {customers_csv.name} ({len(df_customers)} rows)")

    # 1b. Retail Orders (CSV) - Foreign Key to customers
    orders_data = []
    for i in range(1, 301):
        cust_id = f"CUST_{((i * 7) % 100) + 1:04d}"
        orders_data.append({
            "order_id": f"ORD_{i:05d}",
            "customer_id": cust_id,
            "order_date": f"2023-{1 + (i % 12):02d}-{(i % 28) + 1:02d} 14:30:00",
            "amount": round(25.50 + (i * 3.75) % 450, 2),
            "order_status": ["delivered", "shipped", "canceled"][i % 3 if i % 15 == 0 else 0]
        })
    df_orders = pd.DataFrame(orders_data)
    orders_csv = SAMPLE_DIR / "retail_orders.csv"
    df_orders.to_csv(orders_csv, index=False)
    print(f"✅ Generated {orders_csv.name} ({len(df_orders)} rows)")

    # 2. Student Marks (XLSX)
    students_data = []
    subjects = ["Mathematics", "Physics", "Chemistry", "Computer Science", "English"]
    for s_id in range(1, 51):
        for subj in subjects:
            marks = (s_id * 17 + len(subj) * 11) % 60 + 40
            students_data.append({
                "student_id": f"STU_{s_id:03d}",
                "student_name": f"Student {s_id}",
                "subject": subj,
                "marks": marks,
                "exam_date": "2023-11-20",
                "passed": marks >= 50
            })
    df_students = pd.DataFrame(students_data)
    students_xlsx = SAMPLE_DIR / "student_marks.xlsx"
    df_students.to_excel(students_xlsx, index=False, engine="openpyxl")
    print(f"✅ Generated {students_xlsx.name} ({len(df_students)} rows)")

    # 3. Bike Sharing Messy (TSV) - Messy headers, ambiguous dates, constant col, high nulls
    messy_data = []
    for i in range(1, 151):
        messy_data.append({
            "  Trip ID  ": f"TRIP_{i:04d}",
            " start_station ": f"Station_{(i % 10) + 1}",
            "END_STATION": f"Station_{((i + 3) % 10) + 1}",
            " rental_time ": f"{5 + (i % 5):02d}/06/2023 10:15",  # Ambiguous dd/mm vs mm/dd
            "Duration (mins)": 10 + (i % 55),
            " user-type ": "Subscriber" if i % 2 == 0 else "Casual",
            " constant_flag ": "SYSTEM_ACTIVE",  # Constant column
            "NOTES ": f"Delayed {i} mins" if i % 4 == 0 else None  # 75% null
        })
    df_messy = pd.DataFrame(messy_data)
    messy_tsv = SAMPLE_DIR / "bike_sharing_messy.tsv"
    df_messy.to_csv(messy_tsv, sep="\t", index=False)
    print(f"✅ Generated {messy_tsv.name} ({len(df_messy)} rows)")


if __name__ == "__main__":
    generate_sample_datasets()
