import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd
from backend.app.schemas.dataset import ColumnProfile, RelationshipProfile, TableProfile
from backend.app.services.dataset_file_parser import infer_column_type


def determine_column_role(
    col_name: str,
    pg_type: str,
    distinct_count: int,
    total_rows: int,
    is_numeric: bool
) -> str:
    """
    Deterministic rule-based heuristics to classify column analytical role:
    'id', 'datetime', 'measure', 'dimension', 'boolean', 'free_text'.
    """
    lower_name = col_name.lower()

    # 1. ID / Key check
    if re.search(r"(?:^id$|_id$|^uuid$|_uuid$|^code$|_code$|^key$|_key$|^hash$)", lower_name):
        return "id"
    if total_rows > 0 and distinct_count == total_rows and is_numeric and not lower_name.endswith(("_pct", "_rate", "_ratio")):
        if distinct_count > 10:
            return "id"

    # 2. Datetime check
    if pg_type in ("DATE", "TIMESTAMP") or re.search(r"(?:date|time|timestamp|_at$|_on$)", lower_name):
        return "datetime"

    # 3. Boolean check
    if pg_type == "BOOLEAN" or re.search(r"^(?:is_|has_|was_|flag_)", lower_name):
        return "boolean"

    # 4. Measure check (numeric metrics)
    if is_numeric:
        if distinct_count > 15 or re.search(r"(?:amount|revenue|price|cost|freight|value|qty|quantity|count|sum|score|rating|total|avg|rate)", lower_name):
            return "measure"

    # 5. Dimension vs Free Text
    if pg_type == "TEXT":
        if total_rows > 0:
            ratio = distinct_count / total_rows
            if distinct_count <= 50 or ratio < 0.20:
                return "dimension"
        return "free_text"

    return "dimension"


class DatasetProfiler:
    """
    Pure deterministic profiler for tabular data.
    Computes statistical summaries, data quality findings, candidate keys, and multi-table relationships.
    """

    @classmethod
    def profile_dataframe(
        cls,
        df: pd.DataFrame,
        original_table_name: str,
        safe_table_name: str,
        column_mapping: Dict[str, str],
        share_samples: bool = False
    ) -> TableProfile:
        total_rows = len(df)
        column_count = len(df.columns)
        column_profiles: List[ColumnProfile] = []
        quality_findings: List[Dict[str, Any]] = []

        candidate_pk: Optional[str] = None
        best_pk_distinctness = 0.0

        candidate_time_col: Optional[str] = None
        time_cols_found = []

        # 1. Check duplicate rows
        dup_rows = int(df.duplicated().sum()) if total_rows > 0 else 0
        if dup_rows > 0:
            quality_findings.append({
                "type": "duplicate_rows",
                "severity": "medium",
                "message": f"Table contains {dup_rows:,} duplicate rows ({(dup_rows/total_rows*100.0):.1f}%)."
            })

        # Reverse column mapping for original name lookup
        safe_to_original = {safe: orig for orig, safe in column_mapping.items()}

        for col_name in df.columns:
            series = df[col_name]
            orig_name = safe_to_original.get(col_name, col_name)

            # Null percentage
            null_count = int(series.isna().sum())
            null_pct = round((null_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0
            if null_pct > 50.0:
                quality_findings.append({
                    "type": "high_null_column",
                    "column": col_name,
                    "severity": "high" if null_pct > 80.0 else "medium",
                    "message": f"Column '{col_name}' has {null_pct:.1f}% missing values."
                })

            # Non-null values
            non_null_series = series.dropna()
            non_null_count = len(non_null_series)
            distinct_count = int(non_null_series.nunique())

            if distinct_count == 1 and total_rows > 1:
                quality_findings.append({
                    "type": "constant_column",
                    "column": col_name,
                    "severity": "low",
                    "message": f"Column '{col_name}' is constant (all values are identical: '{non_null_series.iloc[0]}')."
                })

            # Infer Type
            sample_vals = non_null_series.head(100).tolist()
            pg_type, _ = infer_column_type(sample_vals)

            is_numeric = pg_type in ("INTEGER", "BIGINT", "NUMERIC(15, 2)")
            stats: Dict[str, Any] = {}
            min_val = None
            max_val = None

            if is_numeric and non_null_count > 0:
                # Convert to numeric for stats
                numeric_series = pd.to_numeric(non_null_series, errors="coerce").dropna()
                if len(numeric_series) > 0:
                    min_val = str(round(float(numeric_series.min()), 2))
                    max_val = str(round(float(numeric_series.max()), 2))
                    stats["mean"] = round(float(numeric_series.mean()), 2)
                    stats["median"] = round(float(numeric_series.median()), 2)
                    std_val = float(numeric_series.std())
                    stats["std"] = round(std_val, 2) if not math.isnan(std_val) else 0.0

                    # Check suspicious negative values for revenue/price/qty
                    if float(numeric_series.min()) < 0 and any(kw in col_name.lower() for kw in ("price", "revenue", "amount", "qty", "quantity", "cost", "freight", "value")):
                        quality_findings.append({
                            "type": "suspicious_negative_values",
                            "column": col_name,
                            "severity": "high",
                            "message": f"Column '{col_name}' contains negative values (min: {min_val})."
                        })
            else:
                if non_null_count > 0:
                    min_val = str(non_null_series.min())[:50]
                    max_val = str(non_null_series.max())[:50]

            # Top 5 values (STORED ONLY IF share_samples IS TRUE)
            if share_samples and distinct_count <= 25 and non_null_count > 0:
                top_items = non_null_series.value_counts().head(5).to_dict()
                stats["top_5"] = [{str(k): int(v)} for k, v in top_items.items()]

            # Determine Role
            role = determine_column_role(col_name, pg_type, distinct_count, total_rows, is_numeric)

            # Evaluate Candidate PK
            if total_rows > 0 and null_count == 0:
                distinctness = distinct_count / total_rows
                if distinctness > best_pk_distinctness and distinctness >= 0.98:
                    best_pk_distinctness = distinctness
                    candidate_pk = col_name

            # Evaluate Candidate Time Column
            if role == "datetime":
                time_cols_found.append(col_name)

            col_prof = ColumnProfile(
                original_name=orig_name,
                safe_name=col_name,
                pg_type=pg_type,
                role=role,
                null_pct=null_pct,
                distinct_count=distinct_count,
                min_val=min_val,
                max_val=max_val,
                stats=stats
            )
            column_profiles.append(col_prof)

        if time_cols_found:
            candidate_time_col = time_cols_found[0]

        return TableProfile(
            original_name=original_table_name,
            safe_name=safe_table_name,
            row_count=total_rows,
            column_count=column_count,
            candidate_pk=candidate_pk,
            candidate_time_column=candidate_time_col,
            quality_findings=quality_findings,
            columns=column_profiles
        )

    @classmethod
    def infer_relationships(
        cls,
        tables_data: Dict[str, pd.DataFrame],
        tables_profiles: Dict[str, TableProfile]
    ) -> List[RelationshipProfile]:
        """
        Infers foreign key relationships across multi-file uploads using:
        1. Name similarity: matching exact column name or parent_pk == child_column (e.g. orders.customer_id -> customers.customer_id)
        2. Value containment: >= 95% of child column values exist in parent column values.
        3. Cardinality: '1:1' if child column is also unique, '1:N' otherwise.
        """
        relationships: List[RelationshipProfile] = []
        table_names = list(tables_data.keys())

        for i in range(len(table_names)):
            for j in range(len(table_names)):
                if i == j:
                    continue

                parent_name = table_names[i]
                child_name = table_names[j]

                parent_df = tables_data[parent_name]
                child_df = tables_data[child_name]

                parent_prof = tables_profiles.get(parent_name)
                if not parent_prof:
                    continue

                # Potential parent PKs
                parent_keys = [c.safe_name for c in parent_prof.columns if c.role == "id" or c.safe_name == parent_prof.candidate_pk]

                for p_col in parent_keys:
                    p_non_null = parent_df[p_col].dropna().astype(str)
                    p_values = set(p_non_null.tolist())
                    if len(p_values) == 0:
                        continue
                    # The parent side of an FK must be unique; an id-named column that repeats
                    # (e.g. orders.customer_id) is itself a foreign key, not a referenced key.
                    if len(p_values) != len(p_non_null):
                        continue

                    for c_col in child_df.columns:
                        # Check name similarity
                        name_match = False
                        if p_col == c_col:
                            name_match = True
                        elif c_col.endswith(f"_{p_col}") or c_col == f"{parent_name}_{p_col}" or p_col == f"{parent_name}_id":
                            name_match = True

                        if not name_match:
                            continue

                        # Check Value Containment (child values in parent values)
                        child_vals = child_df[c_col].dropna().astype(str).tolist()
                        if not child_vals:
                            continue

                        matched_count = sum(1 for v in child_vals if v in p_values)
                        containment = matched_count / len(child_vals)

                        if containment >= 0.95:
                            # Cardinality
                            child_is_unique = (child_df[c_col].dropna().nunique() == len(child_vals))
                            cardinality = "1:1" if child_is_unique else "1:N"

                            confidence = round(float(containment * (0.95 if p_col == c_col else 0.85)), 2)

                            relationships.append(RelationshipProfile(
                                parent_table=parent_name,
                                parent_column=p_col,
                                child_table=child_name,
                                child_column=c_col,
                                cardinality=cardinality,
                                confidence=min(confidence, 1.0),
                                confirmed=False
                            ))

        return relationships
