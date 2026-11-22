import csv
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from backend.app.config import settings
from backend.app.services.dataset_sanitizer import sanitize_column_list, sanitize_table_name


class FileValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# Magic bytes that indicate non-tabular binary files disguised with .csv extension
DISALLOWED_BINARY_SIGNATURES = [
    (b"%PDF", "PDF Document"),
    (b"\x7fELF", "Linux ELF Executable"),
    (b"MZ", "Windows PE Executable"),
    (b"\x89PNG", "PNG Image"),
    (b"\xff\xd8\xff", "JPEG Image"),
    (b"GIF8", "GIF Image"),
    (b"PK\x03\x04", "ZIP Archive"),  # For CSV/TSV files, ZIP magic bytes are invalid
]


def detect_file_encoding(file_path: Path) -> str:
    """
    Detects file encoding checking for UTF-8 BOM, UTF-8 validity, and falling back to Latin-1.
    """
    with open(file_path, "rb") as f:
        head = f.read(65536)

    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    try:
        head.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def detect_delimiter(sample_text: str) -> str:
    """
    Detects column delimiter from CSV text (, \t ; |).
    """
    first_lines = "\n".join(sample_text.splitlines()[:10])
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(first_lines, delimiters=[",", "\t", ";", "|"])
        return dialect.delimiter
    except Exception:
        # Fallback counting
        counts = {
            ",": sample_text.count(","),
            "\t": sample_text.count("\t"),
            ";": sample_text.count(";"),
            "|": sample_text.count("|")
        }
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def check_date_ambiguity(values: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Inspects date strings to detect ambiguous dd/mm vs mm/dd representations.
    Returns (is_ambiguous, sample_date).
    If every observed date with 2 slashes or dashes has both parts <= 12, it is ambiguous.
    """
    ambiguous_count = 0
    total_dates = 0
    first_ambiguous = None

    date_pattern = re.compile(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})(?:[ T](\d{1,2}):(\d{2}))?", re.IGNORECASE)

    for v in values:
        if not v or not isinstance(v, str):
            continue
        v_str = v.strip()
        m = date_pattern.match(v_str)
        if m:
            total_dates += 1
            p1, p2 = int(m.group(1)), int(m.group(2))
            if p1 <= 12 and p2 <= 12:
                ambiguous_count += 1
                if not first_ambiguous:
                    first_ambiguous = v_str

    if total_dates > 0 and ambiguous_count == total_dates:
        return True, first_ambiguous
    return False, None


def infer_column_type(
    values: List[Any],
    col_name: str = "",
    return_format: bool = False
) -> Any:
    """
    Infers PostgreSQL column type and flags date format ambiguity.
    Supports:
      - Boolean
      - Integer & Bigint (signed and unsigned)
      - Numeric/Decimal
      - ISO with T or space (TIMESTAMP/DATE)
      - dd/mm/yyyy and mm/dd/yyyy with and without time (TIMESTAMP/DATE)
      - 12-hour AM/PM timestamps
      - Month names (e.g. 15-Jan-2023, January 15, 2023)
      - Epoch seconds (10-digit) and milliseconds (13-digit)
      - Excel serial dates (30000-65000)
    Returns (pg_type, warning_flag) or (pg_type, warning_flag, dominant_format) if return_format=True.
    """
    non_nulls = [v for v in values if v is not None and str(v).strip() != "" and str(v).lower() != "nan"]
    if not non_nulls:
        return ("TEXT", None, None) if return_format else ("TEXT", None)

    n_total = len(non_nulls)
    str_vals = [str(v).strip() for v in non_nulls]
    lower_col = col_name.lower() if col_name else ""

    # 1. Boolean check
    bool_matches = sum(1 for s in str_vals if s.lower() in ("true", "false", "t", "f", "yes", "no", "1", "0"))
    if bool_matches == n_total and any(s.lower() in ("true", "false", "yes", "no", "t", "f") for s in str_vals):
        return ("BOOLEAN", None, None) if return_format else ("BOOLEAN", None)

    # 2. Datetime: Epoch seconds (10 digits) or milliseconds (13 digits)
    if any(k in lower_col for k in ("time", "date", "ts", "created", "at", "timestamp")):
        epoch_s_matches = sum(1 for s in str_vals if re.match(r"^\d{10}$", s) and 1000000000 <= int(s) <= 2500000000)
        if epoch_s_matches == n_total:
            return ("TIMESTAMP", None, "epoch_s") if return_format else ("TIMESTAMP", None)

        epoch_ms_matches = sum(1 for s in str_vals if re.match(r"^\d{13}$", s) and 1000000000000 <= int(s) <= 2500000000000)
        if epoch_ms_matches == n_total:
            return ("TIMESTAMP", None, "epoch_ms") if return_format else ("TIMESTAMP", None)

    # 3. Datetime: Excel serial dates (e.g. 44927 or 44927.5)
    if any(k in lower_col for k in ("time", "date", "day", "created", "at")):
        excel_matches = []
        has_fraction = False
        for s in str_vals:
            if re.match(r"^\d{4,5}(?:\.\d+)?$", s):
                try:
                    val = float(s)
                    if 30000 <= val <= 65000:
                        excel_matches.append(val)
                        if "." in s and not s.endswith(".0"):
                            has_fraction = True
                except ValueError:
                    pass
        if len(excel_matches) == n_total:
            c_type = "TIMESTAMP" if has_fraction else "DATE"
            return (c_type, None, "excel_serial") if return_format else (c_type, None)

    # 4. Integer check (including signed integers e.g. -2, +3)
    int_matches = sum(1 for s in str_vals if re.match(r"^[+-]?\d+$", s))
    if int_matches == n_total:
        max_abs = max(abs(int(s)) for s in str_vals)
        if max_abs > 2147483647:
            return ("BIGINT", None, None) if return_format else ("BIGINT", None)
        return ("INTEGER", None, None) if return_format else ("INTEGER", None)

    # 5. Numeric / Decimal check (including signed decimals e.g. -5.5, +3.14)
    num_matches = sum(1 for s in str_vals if re.match(r"^[+-]?\d+(?:\.\d+)?$", s))
    if num_matches == n_total:
        return ("NUMERIC(15, 2)", None, None) if return_format else ("NUMERIC(15, 2)", None)

    # 6. Datetime: ISO format
    iso_ts_matches = sum(1 for s in str_vals if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$", s))
    if iso_ts_matches == n_total:
        return ("TIMESTAMP", None, "iso_timestamp") if return_format else ("TIMESTAMP", None)

    iso_date_matches = sum(1 for s in str_vals if re.match(r"^\d{4}-\d{2}-\d{2}$", s))
    if iso_date_matches == n_total:
        return ("DATE", None, "iso_date") if return_format else ("DATE", None)

    # 7. Datetime: Month names (e.g. 15-Jan-2023, January 15, 2023)
    month_pat = re.compile(
        r"^(?:\d{1,2}[/\-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[/\-\s]\d{2,4}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})"
        r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm))?)?$",
        re.IGNORECASE
    )
    month_matches = sum(1 for s in str_vals if month_pat.match(s))
    if month_matches == n_total:
        has_time = any(":" in s for s in str_vals)
        c_type = "TIMESTAMP" if has_time else "DATE"
        return (c_type, None, "month_name") if return_format else (c_type, None)

    # 8. Datetime: Slash / dash dates with or without time & 12-hour AM/PM
    # e.g. 06/06/2023 10:15, 15/01/2023, 01/15/2023 02:30 PM
    slash_pat = re.compile(
        r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*(AM|PM|am|pm))?)?$",
        re.IGNORECASE
    )
    slash_parsed = []
    for s in str_vals:
        m = slash_pat.match(s)
        if m:
            p1 = int(m.group(1))
            p2 = int(m.group(2))
            has_time = m.group(4) is not None
            slash_parsed.append((p1, p2, has_time, s))

    if len(slash_parsed) == n_total:
        any_has_time = any(sp[2] for sp in slash_parsed)
        col_type = "TIMESTAMP" if any_has_time else "DATE"

        all_ambiguous = all(sp[0] <= 12 and sp[1] <= 12 for sp in slash_parsed)
        has_p1_gt_12 = any(sp[0] > 12 for sp in slash_parsed)
        has_p2_gt_12 = any(sp[1] > 12 for sp in slash_parsed)

        if all_ambiguous:
            sample_amb = slash_parsed[0][3]
            warning = f"Ambiguous date format (e.g. '{sample_amb}'): day and month are both <= 12. Override via PATCH /api/datasets/{{id}}/columns with format_override ('dd/mm/yyyy' or 'mm/dd/yyyy')."
            dominant = "dd/mm/yyyy" + (" HH:MM" if any_has_time else "")
            return (col_type, warning, dominant) if return_format else (col_type, warning)
        elif has_p1_gt_12 and not has_p2_gt_12:
            dominant = "dd/mm/yyyy" + (" HH:MM" if any_has_time else "")
            return (col_type, None, dominant) if return_format else (col_type, None)
        elif has_p2_gt_12 and not has_p1_gt_12:
            dominant = "mm/dd/yyyy" + (" HH:MM" if any_has_time else "")
            return (col_type, None, dominant) if return_format else (col_type, None)
        else:
            dominant = "dd/mm/yyyy" + (" HH:MM" if any_has_time else "")
            return (col_type, None, dominant) if return_format else (col_type, None)

    return ("TEXT", None, None) if return_format else ("TEXT", None)


class DatasetFileParser:
    """
    Parses, validates, sanitizes and profiles uploaded CSV, TSV, and XLSX files.
    """

    @classmethod
    def validate_file_content(cls, file_path: Path, filename: str) -> str:
        """
        Validates physical file content against allowed formats (CSV, TSV, XLSX).
        Rejects .xlsm, files with macro streams, and disguised binaries.
        Returns format: 'csv', 'tsv', or 'xlsx'.
        """
        # 1. Path traversal check
        if ".." in filename or "/" in filename or "\\" in filename:
            clean_name = Path(filename).name
        else:
            clean_name = filename

        # 2. Check extension
        ext = clean_name.lower().split(".")[-1] if "." in clean_name else ""
        if ext not in ("csv", "tsv", "xlsx"):
            if ext == "xlsm":
                raise FileValidationError(
                    "Macro-enabled Excel (.xlsm) is not permitted. Only .xlsx, .csv, and .tsv are accepted.",
                    status_code=400
                )
            raise FileValidationError(
                f"Unsupported file format '{ext}'. Allowed formats: .csv, .tsv, .xlsx",
                status_code=415
            )

        # 3. Check file size
        size_bytes = file_path.stat().st_size
        if size_bytes == 0:
            raise FileValidationError("Uploaded file is empty (0 bytes).", status_code=400)

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if size_bytes > max_bytes:
            raise FileValidationError(
                f"File '{clean_name}' ({size_bytes / (1024*1024):.1f} MB) exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB.",
                status_code=413
            )

        # 4. Content magic bytes validation
        with open(file_path, "rb") as f:
            header_bytes = f.read(16)

        if ext == "xlsx":
            # Must be a valid zip file containing Excel workbook
            if not header_bytes.startswith(b"PK\x03\x04"):
                raise FileValidationError(
                    "File has .xlsx extension but is not a valid ZIP/Excel archive.",
                    status_code=400
                )
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    namelist = zf.namelist()
                    # Check for macro payload
                    if any("vbaProject.bin" in name for name in namelist):
                        raise FileValidationError(
                            "Excel file contains embedded VBA macros. Macro-enabled workbooks are not permitted.",
                            status_code=400
                        )
                    # Verify it has Excel structure
                    if not any(name.startswith("xl/") for name in namelist):
                        raise FileValidationError(
                            "ZIP archive does not contain standard Excel workbook parts.",
                            status_code=400
                        )
                    # Decompression bomb protection: check total uncompressed size
                    total_uncompressed = sum(info.file_size for info in zf.infolist())
                    max_uncompressed = settings.XLSX_MAX_UNCOMPRESSED_MB * 1024 * 1024
                    if total_uncompressed > max_uncompressed:
                        raise FileValidationError(
                            f"Excel file decompresses to {total_uncompressed / (1024 * 1024):.0f} MB, "
                            f"exceeding the {settings.XLSX_MAX_UNCOMPRESSED_MB} MB safety limit.",
                            status_code=400
                        )
            except zipfile.BadZipFile:
                raise FileValidationError("Corrupted or invalid Excel .xlsx archive.", status_code=400)
            return "xlsx"

        else:
            # CSV / TSV check: ensure it is not a disguised binary file
            for sig, name in DISALLOWED_BINARY_SIGNATURES:
                if header_bytes.startswith(sig):
                    raise FileValidationError(
                        f"File '{clean_name}' has .{ext} extension but contains {name} binary data.",
                        status_code=400
                    )
            return "tsv" if ext == "tsv" else "csv"

    @classmethod
    def parse_to_dataframe(
        cls,
        file_path: Path,
        filename: str
    ) -> Tuple[pd.DataFrame, str, List[str], Dict[str, str], List[Dict[str, Any]]]:
        """
        Parses an uploaded file into a pandas DataFrame, sanitizes headers,
        and collects column-level warnings (e.g. ambiguous dates).
        Returns:
          - df: Sanitized DataFrame
          - table_name: Sanitized table name
          - safe_columns: List of safe column names
          - mapping: Dict mapping original_name -> safe_name
          - column_warnings: List of {column, warning}
        """
        fmt = cls.validate_file_content(file_path, filename)
        table_name = sanitize_table_name(filename)

        if fmt == "xlsx":
            try:
                import openpyxl
                # openpyxl read_only=True and data_only=True (reads cached formula values)
                wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                sheet_names = wb.sheetnames
                if not sheet_names:
                    wb.close()
                    raise FileValidationError("Excel workbook contains no sheets.", status_code=400)
                # Sheet count guard: too many sheets = slow processing / abuse vector
                if len(sheet_names) > settings.XLSX_MAX_SHEETS:
                    wb.close()
                    raise FileValidationError(
                        f"Excel file has {len(sheet_names)} sheets; maximum allowed is {settings.XLSX_MAX_SHEETS}.",
                        status_code=400
                    )
                ws = wb[sheet_names[0]]

                rows_iter = ws.iter_rows(values_only=True)
                header_row = next(rows_iter, None)
                if not header_row or all(v is None for v in header_row):
                    wb.close()
                    raise FileValidationError("Excel sheet is empty or contains no header row.", status_code=400)

                raw_headers = [str(c).strip() if c is not None else "" for c in header_row]
                data_rows = []
                for row in rows_iter:
                    if len(data_rows) >= settings.MAX_ROWS_PER_TABLE:
                        break
                    # Skip completely empty rows
                    if any(cell is not None for cell in row):
                        data_rows.append(list(row))
                wb.close()

                df = pd.DataFrame(data_rows, columns=raw_headers[:len(data_rows[0])] if data_rows else raw_headers)
            except FileValidationError:
                raise
            except Exception as e:
                raise FileValidationError(f"Failed to parse Excel file: {e}", status_code=400)

        else:
            # CSV / TSV
            encoding = detect_file_encoding(file_path)
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                sample_chunk = f.read(16384)

            delimiter = "\t" if fmt == "tsv" else detect_delimiter(sample_chunk)

            try:
                df = pd.read_csv(
                    file_path,
                    sep=delimiter,
                    encoding=encoding,
                    nrows=settings.MAX_ROWS_PER_TABLE + 5,
                    dtype=str,
                    on_bad_lines="skip"
                )
            except Exception as e:
                raise FileValidationError(f"Failed to parse CSV/TSV file: {e}", status_code=400)

        # Check empty data rows
        if len(df) == 0:
            raise FileValidationError(f"Table '{table_name}' contains headers but no data rows.", status_code=400)

        # Check row limit
        if len(df) > settings.MAX_ROWS_PER_TABLE:
            raise FileValidationError(
                f"Table '{table_name}' exceeds maximum row limit of {settings.MAX_ROWS_PER_TABLE:,} rows.",
                status_code=413
            )

        # Check column limit
        if len(df.columns) > settings.MAX_COLUMNS_PER_TABLE:
            raise FileValidationError(
                f"Table '{table_name}' exceeds maximum column limit of {settings.MAX_COLUMNS_PER_TABLE} columns (provided: {len(df.columns)}).",
                status_code=400
            )

        if len(df.columns) == 0:
            raise FileValidationError("File contains no columns.", status_code=400)

        # Sanitize column identifiers
        raw_cols = list(df.columns)
        safe_cols, mapping = sanitize_column_list(raw_cols)
        df.columns = safe_cols

        # 1. Type inference & warning detection on RAW values first
        # Ensures signed numeric columns e.g. (-5.5, 10, -2, +3) are inferred as NUMERIC/INTEGER
        column_warnings = []
        column_types = {}
        for safe_col in safe_cols:
            vals = df[safe_col].dropna().astype(str).tolist()[:50]
            col_type, warning, dom_fmt = infer_column_type(vals, col_name=safe_col, return_format=True)
            column_types[safe_col] = col_type
            if warning:
                column_warnings.append({"column": safe_col, "warning": warning})

            # Normalize date and timestamp columns to ISO format so PostgreSQL COPY loads cleanly into DATE/TIMESTAMP
            if col_type in ("DATE", "TIMESTAMP"):
                try:
                    if dom_fmt == "epoch_s":
                        dt_series = pd.to_datetime(pd.to_numeric(df[safe_col], errors="coerce"), unit="s")
                    elif dom_fmt == "epoch_ms":
                        dt_series = pd.to_datetime(pd.to_numeric(df[safe_col], errors="coerce"), unit="ms")
                    elif dom_fmt == "excel_serial":
                        dt_series = pd.to_datetime(pd.to_numeric(df[safe_col], errors="coerce"), unit="D", origin="1899-12-30")
                    elif dom_fmt and dom_fmt.startswith("dd/mm"):
                        dt_series = pd.to_datetime(df[safe_col], dayfirst=True, errors="coerce")
                    elif dom_fmt and dom_fmt.startswith("mm/dd"):
                        dt_series = pd.to_datetime(df[safe_col], dayfirst=False, errors="coerce")
                    else:
                        dt_series = pd.to_datetime(df[safe_col], errors="coerce")

                    fmt_str = "%Y-%m-%d %H:%M:%S" if col_type == "TIMESTAMP" else "%Y-%m-%d"
                    if dt_series.notnull().sum() > 0:
                        df[safe_col] = dt_series.dt.strftime(fmt_str).fillna("")
                except Exception as e:
                    logger.debug(f"Date normalization notice for column {safe_col}: {e}")

        # 2. Neutralize formula injection ONLY for columns that remain TEXT
        # Cells starting with = or @, or dangerous DDE syntax (+cmd|... or -cmd|...)
        # are prefixed with \t so spreadsheets treat them as literal text.
        # Plain text like "-" and "+1 plan" keeps equality and grouping semantics.
        def _is_formula(val: str) -> bool:
            if not val or not isinstance(val, str):
                return False
            s = val.strip()
            # =HYPERLINK(...), =SUM(...), @SUM(...)
            if s.startswith("=") or s.startswith("@"):
                return True
            # Dangerous DDE / execution syntax like +cmd|... or -2+3+cmd
            if s.startswith("+") or s.startswith("-"):
                # Exclude plain text: single dash, double dash
                if s in ("-", "+", "--", "---"):
                    return False
                # Exclude plain text labels with spaces like "+1 plan", "- none"
                if re.match(r"^[+-]\d*\s+[A-Za-z]", s):
                    return False
                # Formula with pipe, function, chained expression or identifiers
                if "|" in s or re.search(r"[+\-*/]\s*[A-Za-z_]", s) or re.match(r"^[+-]\s*[A-Za-z_]", s):
                    return True
                return True
            return False

        for safe_col in safe_cols:
            if column_types.get(safe_col) == "TEXT":
                has_formula = False
                sample_formula = ""

                def _neutralize(v):
                    nonlocal has_formula, sample_formula
                    if isinstance(v, str) and _is_formula(v):
                        has_formula = True
                        if not sample_formula:
                            sample_formula = v[:40]
                        return "\t" + v
                    return v

                df[safe_col] = df[safe_col].apply(_neutralize)
                if has_formula:
                    column_warnings.append({
                        "column": safe_col,
                        "warning": f"Formula injection detected in column '{safe_col}' (e.g. '{sample_formula}'); neutralized with tab prefix."
                    })

        return df, table_name, safe_cols, mapping, column_warnings
