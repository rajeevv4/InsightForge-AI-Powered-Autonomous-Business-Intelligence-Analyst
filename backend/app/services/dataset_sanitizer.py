import re
import unicodedata
from typing import Dict, List, Set, Tuple

# Comprehensive PostgreSQL / ANSI SQL reserved words that must not be used as bare identifiers
POSTGRES_RESERVED_WORDS = {
    "all", "analyse", "analyze", "and", "any", "array", "as", "asc", "asymmetric",
    "both", "case", "cast", "check", "collate", "column", "constraint", "create",
    "current_catalog", "current_date", "current_role", "current_time", "current_timestamp",
    "current_user", "default", "deferrable", "desc", "distinct", "do", "else", "end",
    "except", "false", "fetch", "for", "foreign", "from", "grant", "group", "having",
    "in", "initially", "intersect", "into", "lateral", "leading", "limit", "localtime",
    "localtimestamp", "not", "null", "offset", "on", "only", "or", "order", "placing",
    "primary", "references", "returning", "select", "session_user", "some", "symmetric",
    "table", "then", "to", "trailing", "true", "union", "unique", "user", "using",
    "variadic", "when", "where", "window", "with"
}

MAX_IDENTIFIER_LENGTH = 63  # PostgreSQL default NAMEDATALEN - 1


def sanitize_identifier(
    raw_name: str,
    existing_names: Set[str] = None,
    max_len: int = MAX_IDENTIFIER_LENGTH,
    prefix_default: str = "col"
) -> str:
    """
    Sanitizes arbitrary untrusted strings into safe PostgreSQL snake_case identifiers.
    Rules:
    - Normalizes unicode (removes accents/diacritics, strips emoji and non-ASCII).
    - Converts spaces, punctuation, dashes to underscores.
    - Strips leading/trailing underscores and consecutive duplicate underscores.
    - If empty, returns '{prefix_default}_1' or next available.
    - If starts with a digit, prefixes with '{prefix_default}_'.
    - If matches a PostgreSQL reserved keyword, prefixes with '{prefix_default}_'.
    - Truncates to max_len (63 chars default).
    - Deduplicates against existing_names (appending _1, _2 as needed).
    """
    if existing_names is None:
        existing_names = set()

    if not raw_name or not isinstance(raw_name, str):
        candidate = f"{prefix_default}_1"
    else:
        # 1. Normalize unicode (NFKD to decompose accents, then encode ASCII ignore)
        normalized = unicodedata.normalize("NFKD", raw_name)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

        # 2. Convert camelCase to snake_case
        s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", ascii_text)
        lowered = s1.lower()

        # 3. Replace non-alphanumeric chars (punctuation, quotes, SQL injection syntax) with '_'
        cleaned = re.sub(r"[^a-z0-9_]+", "_", lowered)

        # 4. Collapse multiple underscores
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")

        if not cleaned:
            candidate = f"{prefix_default}_1"
        else:
            # 5. Check if starts with a digit
            if cleaned[0].isdigit():
                cleaned = f"{prefix_default}_{cleaned}"

            # 6. Check against reserved SQL keywords
            if cleaned in POSTGRES_RESERVED_WORDS:
                cleaned = f"{prefix_default}_{cleaned}"

            # 7. Truncate to max_len without leaving a trailing underscore
            if len(cleaned) > max_len:
                cleaned = cleaned[:max_len].rstrip("_")

            candidate = cleaned if cleaned else f"{prefix_default}_1"

    # 8. Deduplicate candidate against existing_names
    final_name = candidate
    counter = 1
    while final_name in existing_names:
        suffix = f"_{counter}"
        avail_len = max_len - len(suffix)
        base = candidate[:avail_len].rstrip("_")
        final_name = f"{base}{suffix}"
        counter += 1

    return final_name


def sanitize_column_list(raw_columns: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """
    Sanitizes a list of untrusted column header strings in order.
    Returns:
      - safe_columns: List of safe unique identifiers
      - mapping: Dict mapping original_name -> safe_name
    """
    safe_columns: List[str] = []
    used_names: Set[str] = set()
    mapping: Dict[str, str] = {}

    for idx, raw in enumerate(raw_columns):
        raw_str = str(raw).strip() if raw is not None else ""
        fallback_prefix = f"col_{idx + 1}"
        safe = sanitize_identifier(
            raw_str if raw_str else fallback_prefix,
            existing_names=used_names,
            prefix_default="col"
        )
        safe_columns.append(safe)
        used_names.add(safe)
        # Store original mapping (if empty string, store col_N)
        mapping[raw_str if raw_str else fallback_prefix] = safe

    return safe_columns, mapping


def sanitize_table_name(raw_filename: str, existing_tables: Set[str] = None) -> str:
    """
    Sanitizes a file name (e.g. 'Customer Orders-2024.csv') into a safe table identifier.
    Strips extensions and path traversal prefixes.
    """
    # Strip any directory path components (prevents path traversal)
    clean_base = re.split(r"[\\/]", raw_filename)[-1]
    # Remove file extension (e.g. .csv, .xlsx, .tsv)
    name_without_ext = re.sub(r"\.[^.]+$", "", clean_base)

    return sanitize_identifier(
        name_without_ext,
        existing_names=existing_tables,
        prefix_default="tbl"
    )
