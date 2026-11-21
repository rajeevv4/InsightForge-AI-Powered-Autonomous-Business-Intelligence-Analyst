"""
InsightForge — Guarded SQL Validator (AST-Based)
================================================
Validates and sanitizes Text-to-SQL generated queries using sqlglot AST parsing.
Guarantees:
- Exactly 1 SELECT / UNION query (no DDL/DML, no SET/COPY/CALL/DO)
- Table allow-list enforcement (core tables + analytical views only; excludes ai_audit_log)
- System schema denylist (pg_catalog, information_schema)
- Dangerous function denylist (pg_sleep, pg_read_file, dblink, lo_*, set_config, etc.)
- Cross-join prohibition
- Fan-out join revenue multiplication protection
- Enforced LIMIT <= 500
"""

from typing import Tuple, Optional, Set, List
import sqlglot
from sqlglot import exp

# Allowed Core Tables in the InsightForge Semantic Data Model
ALLOWED_CORE_TABLES: Set[str] = {
    "orders",
    "order_items",
    "customers",
    "products",
    "sellers",
    "order_payments",
    "order_reviews"
}

# Allowed Canonical Analytical Views
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
    "ai_audit_log"
}

# Forbidden System Schemas
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
    "pg_backend_pid",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "system",
    "sys_exec",
    "copy",
    "load_file"
}

MAX_ALLOWED_LIMIT: int = 500


class SQLValidationError(ValueError):
    """Raised when an untrusted SQL query fails AST safety checks."""
    pass


class SQLValidator:
    """
    Deterministic AST-based SQL security validator and sanitizer.
    """

    @classmethod
    def validate(cls, raw_sql: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates raw SQL string.
        Returns:
            (is_valid, sanitized_sql, error_message)
        """
        if not raw_sql or not raw_sql.strip():
            return False, None, "SQL query cannot be empty."

        cleaned = raw_sql.strip().rstrip(";")

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
                exp.Copy, exp.Set
            )):
                return False, None, f"Forbidden statement type detected: {type(node).__name__}."

        # Collect local CTE aliases to allow referencing them in FROM/JOIN
        cte_aliases: Set[str] = set()
        for cte in stmt.find_all(exp.CTE):
            if cte.alias:
                cte_aliases.add(cte.alias.lower())

        # 4. Table allow-list & system schema check
        referenced_tables: List[str] = []
        for table_node in stmt.find_all(exp.Table):
            t_name = table_node.name.lower()
            schema_name = (table_node.db or "").lower()

            # Deny system schemas
            if schema_name in DENIED_SCHEMAS:
                return False, None, f"Access to system schema '{schema_name}' is forbidden."

            # Deny internal audit log
            if t_name in DENIED_TABLES:
                return False, None, f"Access to internal table '{t_name}' is strictly forbidden."

            # If not a CTE alias, check against allow-list
            if t_name not in cte_aliases:
                if t_name not in ALLOWED_TABLES:
                    return False, None, f"Table or view '{t_name}' is not in the allowed tables list."
                referenced_tables.append(t_name)

        # 5. Denylist functions check (including root and subqueries)
        for fn_node in stmt.find_all(exp.Func, exp.Anonymous):
            fn_name = fn_node.name.lower() if hasattr(fn_node, "name") else ""
            if not fn_name:
                continue

            # Check schema qualification on function
            if hasattr(fn_node, "db") and fn_node.db and fn_node.db.lower() in DENIED_SCHEMAS:
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

        # 7. Fan-out join rule: joining order_items AND (order_reviews OR order_payments) while summing revenue
        tables_set = set(referenced_tables)
        if "order_items" in tables_set and ("order_reviews" in tables_set or "order_payments" in tables_set):
            # Check if any SUM expression aggregates revenue/price
            for sum_node in stmt.find_all(exp.Sum):
                sum_sql = sum_node.sql().lower()
                if any(k in sum_sql for k in ["price", "freight_value", "payment_value", "total_amount", "revenue"]):
                    return False, None, (
                        "Fan-out rule violation: joining order_items directly with order_reviews or order_payments "
                        "while aggregating revenue creates duplicate rows. Use view_order_level_summary or pre-aggregate in a CTE."
                    )

        # 8. Delivered status business rule guard:
        # If a query computes revenue/orders/units from orders, order_items, customers, or view_order_level_summary
        # without a delivered-status filter and without using a view that already filters on delivered,
        # return a validation error to trigger self-correction.
        # Legitimate non-financial queries (e.g. status breakdown, canceled orders) are explicitly permitted.
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
                # Exception (a): query groups by order_status (e.g. status distribution)
                groups_by_status = False
                for gb in stmt.find_all(exp.Group):
                    gb_sql = gb.sql().lower()
                    if "order_status" in gb_sql or "status" in gb_sql:
                        groups_by_status = True
                        break

                if not groups_by_status:
                    # Exception (b): query has explicit delivered status filter
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

                    # Exception (c): query explicitly filters for other specific statuses (e.g. 'canceled', 'shipped')
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
        # If top-level statement has limit, clamp it; otherwise append limit(500)
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
