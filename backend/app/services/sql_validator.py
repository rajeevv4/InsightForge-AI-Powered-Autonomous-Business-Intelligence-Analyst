"""
InsightForge — Guarded SQL Validator (AST-Based)
================================================
Validates and sanitizes Text-to-SQL generated queries using sqlglot AST parsing.
Guarantees:
- Exactly 1 SELECT / UNION query (no DDL/DML, no SET/COPY/CALL/DO)
- Table allow-list enforcement (core tables + analytical views for Olist, or dataset schema tables)
- System schema denylist (pg_catalog, information_schema, insightforge, other ds_* schemas)
- Dangerous function denylist (pg_sleep, pg_read_file, dblink, lo_*, set_config, etc.)
- Cross-join prohibition
- Fan-out join protection (Olist fan-out rule or generic 1:N relationship guard)
- Enforced LIMIT <= 500
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Tuple, Optional, Set, List, Dict, Any
import sqlglot
from sqlglot import exp

# Allowed Core Tables in the InsightForge Semantic Data Model (Olist)
ALLOWED_CORE_TABLES: Set[str] = {
    "orders",
    "order_items",
    "customers",
    "products",
    "sellers",
    "order_payments",
    "order_reviews"
}

# Allowed Canonical Analytical Views (Olist)
ALLOWED_ANALYTICAL_VIEWS: Set[str] = {
    "view_order_level_summary",
    "view_monthly_kpis_mom",
    "view_category_contribution",
    "view_state_contribution",
    "view_delivery_sla_performance",
    "view_seller_performance"
}

ALLOWED_TABLES: Set[str] = ALLOWED_CORE_TABLES | ALLOWED_ANALYTICAL_VIEWS

# Explicitly Forbidden Internal Tables
DENIED_TABLES: Set[str] = {
    "ai_audit_log",
    "datasets",
    "dataset_tables",
    "dataset_columns",
    "dataset_relationships",
    "dataset_semantic"
}

# Forbidden Schemas
DENIED_SCHEMAS: Set[str] = {
    "pg_catalog",
    "information_schema",
    "pg_toast",
    "pg_temp"
}

# Dangerous / System Function Denylist
DENIED_FUNCTIONS: Set[str] = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "dblink",
    "dblink_exec",
    "set_config",
    "current_setting",
    "query_to_xml",
    "to_regclass",
    "to_regproc",
    "to_regtype",
    "to_regoper",
    "to_regrole",
    "to_regnamespace",
    "pg_backend_pid",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "system",
    "sys_exec",
    "copy",
    "load_file"
}

MAX_ALLOWED_LIMIT: int = 500


@dataclass
class DatasetSQLContext:
    """Scoped SQL context for dataset workspace queries."""
    schema_name: str
    allowed_tables: Set[str]
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    table_columns: Dict[str, Set[str]] = field(default_factory=dict)
    is_demo: bool = False


class SQLValidationError(ValueError):
    """Raised when an untrusted SQL query fails AST safety checks."""
    pass


class SQLValidator:
    """
    Deterministic AST-based SQL security validator and sanitizer.
    """

    @classmethod
    def validate(
        cls,
        raw_sql: str,
        context: Optional[DatasetSQLContext] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates raw SQL string.
        Returns:
            (is_valid, sanitized_sql, error_message)
        """
        if not raw_sql or not raw_sql.strip():
            return False, None, "SQL query cannot be empty."

        cleaned = raw_sql.strip().rstrip(";")
        # Normalize unicode representation
        cleaned = unicodedata.normalize("NFKC", cleaned)

        # Check for unclosed multiline comment trick
        if "/*" in cleaned and "*/" not in cleaned:
            return False, None, "Unclosed block comment detected."

        # 1. Parse using sqlglot Postgres dialect
        try:
            parsed = sqlglot.parse(cleaned, read="postgres")
        except Exception as e:
            return False, None, f"SQL syntax parsing error: {str(e)}"

        # 2. Enforce exactly one statement
        if len(parsed) != 1:
            return False, None, "Multiple SQL statements are strictly rejected."

        stmt = parsed[0]

        # 3. Only SELECT or UNION queries allowed (no DDL/DML, SET, COPY, CALL)
        if not isinstance(stmt, (exp.Select, exp.Union)):
            return False, None, f"Only SELECT queries are permitted (got {type(stmt).__name__})."

        # Check for DDL/DML or command nodes anywhere in the tree
        for node in stmt.walk():
            if isinstance(node, (
                exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                exp.Alter, exp.TruncateTable, exp.Grant, exp.Revoke, exp.Command,
                exp.Copy, exp.Set, exp.SetItem, exp.Transaction
            )):
                return False, None, f"Forbidden statement type detected: {type(node).__name__}."

        # Collect local CTE aliases to allow referencing them in FROM/JOIN
        cte_aliases: Set[str] = set()
        for cte in stmt.find_all(exp.CTE):
            if cte.alias:
                c_alias = unicodedata.normalize("NFKC", cte.alias).strip().strip('"').lower()
                # Prevent CTEs from shadowing protected schemas or metadata tables
                if (c_alias in DENIED_TABLES or
                    c_alias in DENIED_SCHEMAS or
                    c_alias.startswith("ds_") or
                    c_alias.startswith("pg_") or
                    c_alias in ("insightforge", "information_schema")):
                    return False, None, f"CTE alias '{cte.alias}' conflicts with protected table or schema name."
                cte_aliases.add(c_alias)

        is_custom_dataset = context is not None and not context.is_demo
        expected_schema = context.schema_name.lower() if is_custom_dataset else None
        effective_allowed_tables = {t.lower() for t in context.allowed_tables} if is_custom_dataset else ALLOWED_TABLES

        # 4. Table allow-list & system schema check
        referenced_tables: List[str] = []
        for table_node in stmt.find_all(exp.Table):
            raw_t_name = str(table_node.this.name if hasattr(table_node.this, "name") else table_node.name)
            raw_db_name = str(table_node.db or "")
            t_name = unicodedata.normalize("NFKC", raw_t_name).strip().strip('"').lower()
            schema_name = unicodedata.normalize("NFKC", raw_db_name).strip().strip('"').lower()

            # Unicode lookalike / non-ASCII identifier check
            if not re.match(r"^[a-z0-9_]+$", t_name):
                return False, None, f"Invalid or non-ASCII characters in table identifier: '{t_name}'."
            if schema_name and not re.match(r"^[a-z0-9_]+$", schema_name):
                return False, None, f"Invalid or non-ASCII characters in schema identifier: '{schema_name}'."

            # Deny system schemas and system tables/views
            if schema_name in DENIED_SCHEMAS or schema_name.startswith("pg_") or schema_name == "information_schema":
                return False, None, f"Access to system schema '{schema_name}' is forbidden."

            if t_name.startswith("pg_"):
                return False, None, f"Access to system table/view '{t_name}' is forbidden."

            if is_custom_dataset and schema_name == "insightforge":
                return False, None, "Access to 'insightforge' metadata schema is forbidden."

            # Deny internal audit log or metadata tables
            if t_name in DENIED_TABLES:
                return False, None, f"Access to internal table '{t_name}' is strictly forbidden."

            # Deny dangerous function used as a table / function expression in FROM clause
            if t_name in DENIED_FUNCTIONS:
                return False, None, f"Forbidden database function call: '{t_name}'."

            if is_custom_dataset:
                # If a CTE alias, cannot be schema-qualified (e.g. ds_a.cte or ds_b.cte)
                if t_name in cte_aliases:
                    if schema_name:
                        return False, None, f"CTE alias '{t_name}' cannot be schema-qualified."
                else:
                    if not schema_name:
                        return False, None, (
                            f"Table '{t_name}' must be schema-qualified with '{expected_schema}.{t_name}'."
                        )
                    if schema_name != expected_schema:
                        return False, None, (
                            f"Access to schema '{schema_name}' is forbidden. "
                            f"Queries in this dataset may only access '{expected_schema}'."
                        )
                    if t_name not in effective_allowed_tables:
                        return False, None, (
                            f"Table '{t_name}' is not in the allowed tables list for dataset '{context.schema_name}'."
                        )
                    referenced_tables.append(t_name)
            else:
                # Demo dataset / default Olist checks
                if schema_name and schema_name not in ("", "insightforge", "public"):
                    return False, None, f"Access to schema '{schema_name}' is forbidden."

                # If not a CTE alias, check against allow-list
                if t_name not in cte_aliases:
                    if t_name not in ALLOWED_TABLES:
                        return False, None, f"Table or view '{t_name}' is not in the allowed tables list."
                    referenced_tables.append(t_name)

        # 5. Denylist functions check (including root and subqueries)
        for fn_node in stmt.find_all(exp.Func, exp.Anonymous):
            fn_name = unicodedata.normalize("NFKC", fn_node.name.lower() if hasattr(fn_node, "name") else "").strip().strip('"')
            if not fn_name:
                continue

            # Check schema qualification on function
            if hasattr(fn_node, "db") and fn_node.db:
                fn_schema = unicodedata.normalize("NFKC", str(fn_node.db)).strip().strip('"').lower()
                if fn_schema in DENIED_SCHEMAS or fn_schema.startswith("pg_") or fn_schema == "information_schema":
                    return False, None, f"Function from system schema '{fn_node.db}' is forbidden."

            # Check function denylist
            if fn_name in DENIED_FUNCTIONS or fn_name.startswith("lo_"):
                return False, None, f"Forbidden database function call: '{fn_name}'."

        # 6. Cross-join & comma Cartesian join prohibition
        for join in stmt.find_all(exp.Join):
            kind = getattr(join, "kind", "") or ""
            kind_str = str(kind).upper()
            if "CROSS" in kind_str or join.args.get("kind") == "CROSS":
                return False, None, "Cross joins (CROSS JOIN) are strictly forbidden."
            if not join.args.get("on") and not join.args.get("using"):
                return False, None, "Cartesian joins without ON/USING clauses are strictly forbidden. Use explicit INNER/LEFT JOIN."

        # 7. Fan-out join rule & guards
        tables_set = set(referenced_tables)

        if is_custom_dataset:
            # Generic fan-out guard for uploaded datasets using inferred/confirmed 1:N relationships
            # If query joins a parent table (1) and a child table (N) directly in a SELECT scope,
            # and computes SUM/AVG on a measure column from the parent table without pre-aggregating in a CTE/subquery.
            if context and context.relationships:
                for rel in context.relationships:
                    cardinality = str(rel.get("cardinality", "")).upper()
                    if cardinality in ("1:N", "1:MANY"):
                        p_tab = str(rel.get("parent_table", "")).lower()
                        c_tab = str(rel.get("child_table", "")).lower()

                        if p_tab in tables_set and c_tab in tables_set:
                            # Check every Select node that directly joins both p_tab and c_tab
                            for select_node in stmt.find_all(exp.Select):
                                direct_tables = set()
                                from_clause = select_node.args.get("from_")
                                if from_clause and isinstance(from_clause.this, exp.Table):
                                    direct_tables.add(from_clause.this.name.lower())
                                for join in select_node.args.get("joins", []):
                                    if isinstance(join.this, exp.Table):
                                        direct_tables.add(join.this.name.lower())

                                if p_tab in direct_tables and c_tab in direct_tables:
                                    # Both tables joined directly in this select scope!
                                    # Build table alias mapping for this select scope
                                    table_alias_map = {}
                                    if from_clause and isinstance(from_clause.this, exp.Table):
                                        t_real = from_clause.this.name.lower()
                                        table_alias_map[t_real] = t_real
                                        if from_clause.this.alias:
                                            table_alias_map[from_clause.this.alias.lower()] = t_real
                                    for join in select_node.args.get("joins", []):
                                        if isinstance(join.this, exp.Table):
                                            t_real = join.this.name.lower()
                                            table_alias_map[t_real] = t_real
                                            if join.this.alias:
                                                table_alias_map[join.this.alias.lower()] = t_real

                                    # Check if any SUM or AVG aggregates a column from p_tab
                                    p_cols = context.table_columns.get(p_tab, set())
                                    for agg_node in select_node.find_all(exp.Sum, exp.Avg):
                                        for col_node in agg_node.find_all(exp.Column):
                                            col_table = (col_node.table or "").lower()
                                            col_name = col_node.name.lower()
                                            resolved_table = table_alias_map.get(col_table, col_table)

                                            is_parent_col = False
                                            if resolved_table == p_tab:
                                                is_parent_col = True
                                            elif not col_table and col_name in p_cols:
                                                c_cols = context.table_columns.get(c_tab, set())
                                                if col_name not in c_cols:
                                                    is_parent_col = True

                                            if is_parent_col:
                                                return False, None, (
                                                    f"Fan-out rule violation: joining '{p_tab}' (one) with '{c_tab}' (many) "
                                                    f"while aggregating '{col_name}' from '{p_tab}' creates duplicate rows. "
                                                    f"Pre-aggregate in a CTE or subquery first."
                                                )
        else:
            # Olist-specific fan-out join rule
            if "order_items" in tables_set and ("order_reviews" in tables_set or "order_payments" in tables_set):
                for sum_node in stmt.find_all(exp.Sum):
                    sum_sql = sum_node.sql().lower()
                    if any(k in sum_sql for k in ["price", "freight_value", "payment_value", "total_amount", "revenue"]):
                        return False, None, (
                            "Fan-out rule violation: joining order_items directly with order_reviews or order_payments "
                            "while aggregating revenue creates duplicate rows. Use view_order_level_summary or pre-aggregate in a CTE."
                        )

            # 8. Delivered status business rule guard (Olist only)
            target_tables = {"orders", "order_items", "customers", "view_order_level_summary"}
            prefiltered_views = {"view_monthly_kpis_mom", "view_category_contribution", "view_delivery_sla_performance"}

            if tables_set.intersection(target_tables) and not tables_set.issubset(prefiltered_views):
                has_financial_or_volume_agg = False
                for agg_node in stmt.find_all(exp.Sum, exp.Count, exp.Avg):
                    agg_sql = agg_node.sql().lower()
                    if any(w in agg_sql for w in ["price", "freight", "amount", "revenue", "order_id", "order_item", "item_count", "*"]):
                        has_financial_or_volume_agg = True
                        break

                if has_financial_or_volume_agg:
                    groups_by_status = False
                    for gb in stmt.find_all(exp.Group):
                        gb_sql = gb.sql().lower()
                        if "order_status" in gb_sql or "status" in gb_sql:
                            groups_by_status = True
                            break

                    if not groups_by_status:
                        full_sql_lower = stmt.sql().lower()
                        where_nodes = list(stmt.find_all(exp.Where))
                        has_status_filter = False
                        has_delivered_filter = False

                        for w in where_nodes:
                            w_sql = w.sql().lower()
                            if "order_status" in w_sql or "status" in w_sql:
                                has_status_filter = True
                                if "'delivered'" in w_sql or '"delivered"' in w_sql:
                                    has_delivered_filter = True

                        is_explicit_other_status = False
                        if has_status_filter and not has_delivered_filter:
                            other_statuses = ["'canceled'", "'unavailable'", "'shipped'", "'invoiced'", "'processing'", "'created'"]
                            if any(s in full_sql_lower for s in other_statuses) or "!=" in full_sql_lower or "<>" in full_sql_lower:
                                is_explicit_other_status = True

                        if not has_delivered_filter and not is_explicit_other_status:
                            return False, None, (
                                "Business rule violation: Queries computing revenue, orders, or volume metrics from orders/order_items "
                                "must filter on delivered orders (e.g. WHERE order_status = 'delivered') unless specifically analyzing other statuses or grouping by order_status."
                            )

        # 9. Force LIMIT <= 500
        try:
            limit_exp = stmt.args.get("limit")
            if limit_exp:
                val_node = limit_exp.expression
                val = int(val_node.name if hasattr(val_node, "name") else str(val_node))
                if val > MAX_ALLOWED_LIMIT or val <= 0:
                    stmt = stmt.limit(MAX_ALLOWED_LIMIT)
            else:
                stmt = stmt.limit(MAX_ALLOWED_LIMIT)
        except Exception:
            stmt = stmt.limit(MAX_ALLOWED_LIMIT)

        # 10. Strip comments from AST (neutralizes comment tricks) and emit clean Postgres SQL
        for node in stmt.walk():
            node.comments = None

        sanitized_sql = stmt.sql(dialect="postgres")
        return True, sanitized_sql, None
