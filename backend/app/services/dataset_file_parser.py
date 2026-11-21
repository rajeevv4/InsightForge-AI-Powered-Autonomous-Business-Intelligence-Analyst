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

    date_pattern = re.compile(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$")

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


def infer_column_type(values: List[Any]) -> Tuple[str, Optional[str]]:
    """
    Infers PostgreSQL column type and flags date format ambiguity.
    Returns (pg_type, warning_flag).
    """
    non_nulls = [v for v in values if v is not None and str(v).strip() != "" and str(v).lower() != "nan"]
    if not non_nulls:
        return "TEXT", None

    n_total = len(non_nulls)
    str_vals = [str(v).strip() for v in non_nulls]

    # 1. Boolean check
    bool_matches = sum(1 for s in str_vals if s.lower() in ("true", "false", "t", "f", "yes", "no", "1", "0"))
    if bool_matches == n_total and any(s.lower() in ("true", "false", "yes", "no", "t", "f") for s in str_vals):
        return "BOOLEAN", None

    # 2. Integer check
    int_matches = sum(1 for s in str_vals if re.match(r"^-?\d+$", s))
    if int_matches == n_total:
        # Check range
        max_abs = max(abs(int(s)) for s in str_vals)
        if max_abs > 2147483647:
            return "BIGINT", None
        return "INTEGER", None

    # 3. Numeric / Decimal check
    num_matches = sum(1 for s in str_vals if re.match(r"^-?\d+(?:\.\d+)?$", s))
    if num_matches == n_total:
        return "NUMERIC(15, 2)", None

    # 4. Date and Timestamp check
    is_ambiguous, sample_amb = check_date_ambiguity(str_vals)
    warning = None
    if is_ambiguous:
        warning = f"Ambiguous date format (e.g. '{sample_amb}'): day and month are both <= 12."

    iso_date_matches = sum(1 for s in str_vals if re.match(r"^\d{4}-\d{2}-\d{2}$", s))
    if iso_date_matches == n_total:
        return "DATE", warning

    iso_timestamp_matches = sum(1 for s in str_vals if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?", s))
    if iso_timestamp_matches == n_total:
        return "TIMESTAMP", warning

    slash_date_matches = sum(1 for s in str_vals if re.match(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$", s))
    if slash_date_matches == n_total:
        return "DATE", warning

    return "TEXT", None


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

        # Formula injection neutralization: prefix cells starting with = + - @ with a tab
        # so they cannot be interpreted as spreadsheet formulas if re-exported.
        # We store the prefixed string in the database (TEXT column); the prefix is harmless.
        _FORMULA_PREFIX_CHARS = ("=", "+", "-", "@")
        for col in df.columns:
            # Apply to all string/object dtype columns
            if pd.api.types.is_string_dtype(df[col]) or df[col].dtype.kind in ("O", "S", "U"):
                df[col] = df[col].apply(
                    lambda v: ("\t" + v)
                    if isinstance(v, str) and v and v[0] in _FORMULA_PREFIX_CHARS
                    else v
                )

        # Detect warnings (e.g. ambiguous date formats)
        column_warnings = []
        for safe_col in safe_cols:
            vals = df[safe_col].dropna().astype(str).tolist()[:50]
            _, warning = infer_column_type(vals)
            if warning:
                column_warnings.append({"column": safe_col, "warning": warning})

        return df, table_name, safe_cols, mapping, column_warnings
