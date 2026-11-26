"""
Dataset Navigation Service (uploaded datasets only)
===================================================
Decides which sidebar sections apply to an uploaded dataset, so the rule lives in
one tested place (GET /api/datasets/{id}/navigation). Deterministic; no LLM.

Sections:
- Core (always): Overview, Datasets, Ask InsightForge, Analytics, Data Quality, Anomalies
- One item per table (label derived from the table name)
- Topic groups, shown only when a column name matches NAV_GROUP_KEYWORDS below

The Olist demo keeps its fixed sidebar in the frontend and never calls this.
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.dataset import DatasetProfile
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService

# ---------------------------------------------------------------------------
# Topic-group keyword rules (THE single place to edit).
#
# A group is shown when at least one column "matches" one of its keywords.
# Matching is on whole name tokens, not substrings: a column name is split on
# non-alphanumeric characters ("customer_city" -> customer, city) and a keyword
# matches a token equal to it, or its plural (+s / +es). Multi-word keywords
# such as "lead_time" must appear as consecutive tokens.
# So "city" matches "city" and "customer_city" but not "capacity"; "state"
# matches "state" / "states" but not "statement" or "estate".
#
#   source = "dimensions": the group looks at semantic-model dimensions (column
#            names, display names and synonyms) PLUS every column name, because a
#            numeric pincode/zip column is drafted as a measure, not a dimension.
#            Falls back to column names alone if the semantic model is unavailable.
#   source = "columns":    the group looks at every column of every table.
# ---------------------------------------------------------------------------
NAV_GROUP_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "geography": {
        "label": "Geography",
        "path": "/geography",
        "source": "dimensions",
        "keywords": ["city", "state", "country", "region", "district", "pincode", "zip", "location"],
    },
    "sellers": {
        "label": "Sellers",
        "path": "/sellers",
        "source": "columns",
        "keywords": ["seller", "vendor", "merchant", "supplier"],
    },
    "payments": {
        "label": "Payments",
        "path": "/payments",
        "source": "columns",
        "keywords": ["payment", "method", "mode", "installment"],
    },
    "delivery": {
        "label": "Delivery",
        "path": "/delivery",
        "source": "columns",
        "keywords": ["delivery", "shipping", "dispatch", "lead_time"],
    },
}

CORE_BEFORE_TABLES = [
    ("overview", "Overview", "/"),
    ("datasets", "Datasets", "/datasets"),
    ("ask", "Ask InsightForge", "/ask"),
    ("analytics", "Analytics", "/analytics"),
]
CORE_AFTER_GROUPS = [
    ("data_quality", "Data Quality", "/data-quality"),
    ("anomalies", "Anomalies", "/anomalies"),
    ("forecast", "Forecast", "/forecast"),
    ("report", "Report", "/report"),
]


class NavigationItem(BaseModel):
    key: str
    label: str
    path: str
    kind: str = Field(description="'core' | 'table' | 'group'")
    table: Optional[str] = None
    matched_columns: List[str] = Field(default_factory=list, description="table.column that triggered a group")


class HiddenNavigationItem(BaseModel):
    key: str
    label: str
    reason: str


class DatasetNavigationResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    items: List[NavigationItem]
    hidden: List[HiddenNavigationItem] = Field(default_factory=list)
    semantic_model_used: bool = Field(description="False if the semantic model was unavailable and only profile columns were used")


def name_tokens(name: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t]


def keyword_matches(name: str, keyword: str) -> bool:
    """Whole-token match of `keyword` (possibly multi-token, e.g. lead_time) in `name`; allows +s/+es plurals."""
    tokens = name_tokens(name)
    kw = name_tokens(keyword)
    if not kw or len(kw) > len(tokens):
        return False
    for i in range(len(tokens) - len(kw) + 1):
        window = tokens[i:i + len(kw)]
        head_ok = window[:-1] == kw[:-1]
        last, kw_last = window[-1], kw[-1]
        if head_ok and last in (kw_last, kw_last + "s", kw_last + "es"):
            return True
    return False


def table_label(safe_name: str) -> str:
    return " ".join(t.capitalize() for t in name_tokens(safe_name)) or safe_name


class DatasetNavigationService:

    @staticmethod
    def build_navigation(profile: DatasetProfile, dimension_names: Optional[Dict[str, List[str]]] = None
                         ) -> DatasetNavigationResponse:
        """
        Pure function (no DB): profile + optional {"table.column": [names/synonyms]} for semantic dimensions.
        """
        items: List[NavigationItem] = [NavigationItem(key=k, label=l, path=p, kind="core") for k, l, p in CORE_BEFORE_TABLES]
        hidden: List[HiddenNavigationItem] = []

        for t in profile.tables:
            items.append(NavigationItem(key=f"table:{t.safe_name}", label=table_label(t.safe_name),
                                        path=f"/tables/{t.safe_name}", kind="table", table=t.safe_name))

        all_columns = {f"{t.safe_name}.{c.safe_name}": [c.safe_name] for t in profile.tables for c in t.columns}
        with_dimensions = dict(all_columns)
        for qualified, names in (dimension_names or {}).items():
            with_dimensions[qualified] = with_dimensions.get(qualified, []) + list(names)
        for key, rule in NAV_GROUP_KEYWORDS.items():
            candidates = with_dimensions if rule["source"] == "dimensions" else all_columns
            matched = sorted(
                qualified for qualified, names in candidates.items()
                if any(keyword_matches(n, kw) for n in names for kw in rule["keywords"])
            )
            if matched:
                items.append(NavigationItem(key=key, label=rule["label"], path=rule["path"], kind="group", matched_columns=matched))
            else:
                hidden.append(HiddenNavigationItem(
                    key=key, label=rule["label"],
                    reason=f"no column matches: {', '.join(rule['keywords'])}",
                ))

        items.extend(NavigationItem(key=k, label=l, path=p, kind="core") for k, l, p in CORE_AFTER_GROUPS)
        return DatasetNavigationResponse(
            dataset_id=profile.id, dataset_name=profile.name, items=items, hidden=hidden,
            semantic_model_used=dimension_names is not None,
        )

    @classmethod
    def get_navigation(cls, dataset_id: str, owner_token: Optional[str] = None) -> DatasetNavigationResponse:
        # Owner isolation: wrong/missing token -> 403, unknown id -> 404
        profile: DatasetProfile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)
        if profile.is_demo or profile.schema_name == "insightforge":
            raise FileValidationError("Navigation is computed only for uploaded datasets; the Olist demo uses its fixed sidebar.", status_code=400)

        dimension_names: Optional[Dict[str, List[str]]] = None
        try:
            model = DatasetSemanticService.get_semantic(dataset_id, owner_token=owner_token, allow_llm=False).semantic_model
            dimension_names = {}
            for d in model.dimensions:
                if d.column:
                    dimension_names[f"{d.table}.{d.column}"] = [d.column, d.name] + list(d.synonyms or [])
        except Exception:
            dimension_names = None  # fall back to profile columns; navigation must not fail

        return cls.build_navigation(profile, dimension_names)
