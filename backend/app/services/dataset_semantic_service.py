import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import engine
from backend.app.exceptions import DatabaseUnavailableError
from backend.app.fixture_guard import is_fixture_mode
from backend.app.schemas.dataset import DatasetProfile, TableProfile, ColumnProfile
from backend.app.schemas.dataset_semantic import (
    CandidateKeyDefinition,
    DatasetSemanticResponse,
    DimensionDefinition,
    MeasureDefinition,
    RelationshipDefinition,
    SemanticModel,
    TimeColumnDefinition,
    UpdateDatasetSemanticRequest,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# Original keywords (unchanged behaviour) -> AVG
_AVG_KEYWORDS_ORIGINAL = ["rate", "avg", "score", "percentage", "pct", "ratio", "duration", "delay", "marks"]
# Added keywords -> AVG ("rating" is not matched by "rate"; summing ratings/days/percents/unit prices is meaningless)
_AVG_KEYWORDS_ADDED = ["rating", "days", "percent", "unit_price"]
# Genuine totals stay SUM even if an added keyword also appears (e.g. total_days).
# Matched as whole name tokens, so "discount_percent" is not caught by "count".
_SUM_GUARD_TOKENS = {"total", "amount", "revenue", "sales", "quantity", "qty", "count"}


def pick_default_aggregation(column_name: str) -> str:
    """Default aggregation for an auto-drafted measure: 'AVG' or 'SUM'."""
    c_lower = column_name.lower()
    if any(k in c_lower for k in _AVG_KEYWORDS_ORIGINAL):
        return "AVG"
    tokens = set(re.split(r"[^a-z0-9]+", c_lower))
    if any(k in c_lower for k in _AVG_KEYWORDS_ADDED) and not (tokens & _SUM_GUARD_TOKENS):
        return "AVG"
    return "SUM"


class DatasetSemanticService:
    """
    Manages semantic layer modeling, deterministic drafting, optional schema-only
    Gemini enrichment, and starter questions for dataset workspace.
    """

    @classmethod
    def _ensure_table(cls):
        """Idempotently ensures insightforge.dataset_semantic exists with proper permissions."""
        if is_fixture_mode():
            return
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE SCHEMA IF NOT EXISTS insightforge;
                    CREATE TABLE IF NOT EXISTS insightforge.dataset_semantic (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        dataset_id UUID NOT NULL REFERENCES insightforge.datasets(id) ON DELETE CASCADE UNIQUE,
                        status VARCHAR(32) NOT NULL DEFAULT 'draft',
                        semantic_model JSONB NOT NULL DEFAULT '{}'::jsonb,
                        starter_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_dataset_semantic_dataset ON insightforge.dataset_semantic(dataset_id);
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'insightforge_ro') THEN
                            REVOKE ALL ON insightforge.dataset_semantic FROM insightforge_ro;
                        END IF;
                    END $$;
                """))
        except Exception as e:
            logger.warning(f"Could not verify/create dataset_semantic table: {e}")

    @classmethod
    def generate_draft(
        cls,
        dataset_id: str,
        owner_token: Optional[str] = None,
        allow_llm: bool = True
    ) -> DatasetSemanticResponse:
        """
        Builds a deterministic semantic layer draft from dataset profile,
        with optional schema-only Gemini enrichment.
        """
        cls._ensure_table()
        profile: DatasetProfile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)

        measures: List[MeasureDefinition] = []
        dimensions: List[DimensionDefinition] = []
        time_columns: List[TimeColumnDefinition] = []
        candidate_keys: List[CandidateKeyDefinition] = []
        relationships: List[RelationshipDefinition] = []

        # 1. Inspect tables & columns
        for table in profile.tables:
            t_name = table.safe_name

            # Add Row Count Measure for table
            measures.append(MeasureDefinition(
                name=f"{t_name.replace('_', ' ').title()} Row Count",
                safe_name=f"{t_name}_count",
                table=t_name,
                column=None,
                aggregation="COUNT",
                formula="COUNT(*)",
                description=f"Total record count in table {t_name}",
                synonyms=["rows", "count", "number of records", "kul sankhya"]
            ))

            # Candidate PK
            if table.candidate_pk:
                candidate_keys.append(CandidateKeyDefinition(
                    table=t_name,
                    column=table.candidate_pk
                ))

            for col in table.columns:
                c_name = col.safe_name
                pg_type = col.pg_type.upper()
                role = col.role.lower()

                # Time columns
                if role == "datetime" or "TIMESTAMP" in pg_type or "DATE" in pg_type or c_name == table.candidate_time_column:
                    time_columns.append(TimeColumnDefinition(
                        name=c_name.replace("_", " ").title(),
                        safe_name=c_name,
                        table=t_name,
                        column=c_name,
                        data_type=col.pg_type
                    ))

                # Measures
                is_numeric_type = any(t in pg_type for t in ["INT", "NUMERIC", "FLOAT", "DOUBLE", "REAL", "DECIMAL"])
                is_id_like = c_name.endswith("_id") or c_name == table.candidate_pk
                is_measure_role = (role == "measure")

                if (is_measure_role or is_numeric_type) and not (is_id_like and not is_measure_role):
                    # Pick aggregation: AVG for score/rate/rating/pct/days/unit price..., else SUM
                    agg = pick_default_aggregation(c_name)

                    measures.append(MeasureDefinition(
                        name=c_name.replace("_", " ").title(),
                        safe_name=f"{t_name}_{c_name}",
                        table=t_name,
                        column=c_name,
                        aggregation=agg,
                        formula=f"{agg}({t_name}.{c_name})",
                        description=col.user_description or f"{agg} of {c_name} in {t_name}",
                        synonyms=[c_name, c_name.replace("_", " ")]
                    ))

                # Dimensions
                if role in ("dimension", "boolean") or (not is_numeric_type and role != "datetime"):
                    dimensions.append(DimensionDefinition(
                        name=c_name.replace("_", " ").title(),
                        safe_name=f"{t_name}_{c_name}",
                        table=t_name,
                        column=c_name,
                        data_type=col.pg_type,
                        description=col.user_description or f"Dimension {c_name} in {t_name}",
                        synonyms=[c_name, c_name.replace("_", " ")]
                    ))

        # 2. Relationships
        for rel in profile.relationships:
            relationships.append(RelationshipDefinition(
                parent_table=rel.parent_table,
                parent_column=rel.parent_column,
                child_table=rel.child_table,
                child_column=rel.child_column,
                cardinality=rel.cardinality,
                confirmed=rel.confirmed
            ))

        # 3. Generate 6-8 deterministic starter questions
        starter_questions = cls._generate_starter_questions(measures, dimensions, time_columns, profile.tables)

        # 4. Optional Schema-Only Gemini Enrichment
        # allow_llm=False: dataset pages (overview/analytics/...) must stay deterministic.
        if allow_llm and not is_fixture_mode() and settings.GEMINI_API_KEY and genai:
            try:
                cls._enrich_schema_with_gemini(
                    profile=profile,
                    measures=measures,
                    dimensions=dimensions,
                    share_samples=profile.share_samples
                )
            except Exception as e:
                logger.info(f"Gemini schema enrichment skipped or failed (using deterministic draft): {e}")

        # Assemble model
        model = SemanticModel(
            dataset_id=profile.id,
            dataset_name=profile.name,
            measures=measures,
            dimensions=dimensions,
            time_columns=time_columns,
            candidate_keys=candidate_keys,
            relationships=relationships,
            user_notes="Generated deterministic semantic draft"
        )

        now = datetime.now(timezone.utc)
        response = DatasetSemanticResponse(
            dataset_id=profile.id,
            status="draft",
            semantic_model=model,
            starter_questions=starter_questions,
            created_at=now,
            updated_at=now
        )

        # Persist to database if not in fixture mode
        if not is_fixture_mode():
            cls._save_to_db(response)

        return response

    @classmethod
    def _generate_starter_questions(
        cls,
        measures: List[MeasureDefinition],
        dimensions: List[DimensionDefinition],
        time_columns: List[TimeColumnDefinition],
        tables: List[TableProfile]
    ) -> List[str]:
        """Generates 6-8 deterministic template questions without calling any LLM."""
        questions: List[str] = []

        # Find primary non-count measure if available, else first measure
        numeric_measures = [m for m in measures if m.column is not None]
        main_measure = numeric_measures[0] if numeric_measures else measures[0]
        second_measure = numeric_measures[1] if len(numeric_measures) > 1 else None

        # Find primary dimensions
        main_dim = dimensions[0] if dimensions else None
        second_dim = dimensions[1] if len(dimensions) > 1 else None

        # Template 1: Total measure by dimension
        if main_dim:
            questions.append(f"Total {main_measure.name} by {main_dim.name}")
        else:
            questions.append(f"What is the overall total {main_measure.name}?")

        # Template 2: Time trend
        if time_columns:
            questions.append(f"{main_measure.name} trend over time by {time_columns[0].name}")
        elif main_dim:
            questions.append(f"Average {main_measure.name} across each {main_dim.name}")

        # Template 3: Top 10 dimension by measure
        if main_dim:
            questions.append(f"Top 10 {main_dim.name} by {main_measure.name}")

        # Template 4: Row count per dimension
        if main_dim:
            questions.append(f"How many records per {main_dim.name}?")

        # Template 5: Average measure by dimension
        if main_dim:
            questions.append(f"Average {main_measure.name} by {main_dim.name}")

        # Template 6: Distribution of dimension
        if second_dim:
            questions.append(f"Distribution of records by {second_dim.name}")
        elif main_dim:
            questions.append(f"Breakdown of {main_dim.name}")

        # Template 7: Second measure or ranking
        if second_measure and main_dim:
            questions.append(f"Total {second_measure.name} by {main_dim.name}")
        elif second_dim and main_measure:
            questions.append(f"Top {second_dim.name} by {main_measure.name}")
        else:
            questions.append(f"Highest and lowest {main_measure.name}")

        # Template 8: Table overview
        if tables:
            questions.append(f"Summary statistics for table {tables[0].safe_name}")

        # Ensure between 6 and 8 questions
        return questions[:8]

    @classmethod
    def _enrich_schema_with_gemini(
        cls,
        profile: DatasetProfile,
        measures: List[MeasureDefinition],
        dimensions: List[DimensionDefinition],
        share_samples: bool
    ):
        """
        Enriches friendly names and synonyms using SCHEMA ONLY.
        NEVER includes cell values unless share_samples is True.
        """
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Build schema-only catalog
        schema_lines = []
        for t in profile.tables:
            cols_info = [f"{c.safe_name} ({c.pg_type}, role={c.role})" for c in t.columns]
            schema_lines.append(f"Table '{t.safe_name}': " + ", ".join(cols_info))

        prompt = f"""
You are a Data Semantic Modeling Assistant.
Analyze this database schema and suggest business-friendly display names and synonyms (in English and Hindi) for key measures and dimensions.

STRICT PRIVACY GUARD: Do NOT invent or infer data values. Only use column names and types provided.

Schema:
{chr(10).join(schema_lines)}

Respond ONLY with a JSON object in this format:
{{
  "measures": {{
    "column_name": {{
      "friendly_name": "...",
      "synonyms": ["synonym 1", "hindi_synonym"]
    }}
  }},
  "dimensions": {{
    "column_name": {{
      "friendly_name": "...",
      "synonyms": ["synonym 1", "hindi_synonym"]
    }}
  }}
}}
"""
        gen_config = types.GenerateContentConfig(temperature=0.0) if types else None
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=gen_config
        )
        text_resp = response.text.strip()
        cleaned = text_resp.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)

        measure_enrich = parsed.get("measures", {})
        dimension_enrich = parsed.get("dimensions", {})

        # Apply strictly to existing measures
        for m in measures:
            if m.column and m.column in measure_enrich:
                data = measure_enrich[m.column]
                if isinstance(data, dict):
                    if data.get("friendly_name"):
                        m.name = str(data["friendly_name"])
                    if isinstance(data.get("synonyms"), list):
                        m.synonyms = list(set(m.synonyms + [str(s) for s in data["synonyms"]]))

        # Apply strictly to existing dimensions
        for d in dimensions:
            if d.column in dimension_enrich:
                data = dimension_enrich[d.column]
                if isinstance(data, dict):
                    if data.get("friendly_name"):
                        d.name = str(data["friendly_name"])
                    if isinstance(data.get("synonyms"), list):
                        d.synonyms = list(set(d.synonyms + [str(s) for s in data["synonyms"]]))

    @classmethod
    def _save_to_db(cls, response: DatasetSemanticResponse):
        """Upserts semantic model into insightforge.dataset_semantic."""
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO insightforge.dataset_semantic (
                        dataset_id, status, semantic_model, starter_questions, updated_at
                    ) VALUES (
                        :dataset_id, :status, :semantic_model, :starter_questions, NOW()
                    ) ON CONFLICT (dataset_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        semantic_model = EXCLUDED.semantic_model,
                        starter_questions = EXCLUDED.starter_questions,
                        updated_at = NOW();
                """),
                {
                    "dataset_id": response.dataset_id,
                    "status": response.status,
                    "semantic_model": response.semantic_model.model_dump_json(),
                    "starter_questions": json.dumps(response.starter_questions)
                }
            )

    @classmethod
    def get_semantic(
        cls,
        dataset_id: str,
        owner_token: Optional[str] = None,
        allow_llm: bool = True
    ) -> DatasetSemanticResponse:
        """Retrieves semantic layer for dataset, generating draft if not exists."""
        cls._ensure_table()
        # Verify owner access via get_dataset_profile
        profile: DatasetProfile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)

        if is_fixture_mode():
            # Deterministic draft in fixture mode
            return cls.generate_draft(dataset_id, owner_token=owner_token, allow_llm=allow_llm)

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM insightforge.dataset_semantic WHERE dataset_id = :id;"),
                {"id": profile.id}
            ).fetchone()

        if not row:
            # Generate draft
            return cls.generate_draft(dataset_id, owner_token=owner_token, allow_llm=allow_llm)

        sem_model_raw = row.semantic_model
        if isinstance(sem_model_raw, str):
            sem_model_data = json.loads(sem_model_raw)
        else:
            sem_model_data = sem_model_raw or {}

        questions_raw = row.starter_questions
        if isinstance(questions_raw, str):
            questions = json.loads(questions_raw)
        else:
            questions = questions_raw or []

        return DatasetSemanticResponse(
            dataset_id=str(row.dataset_id),
            status=row.status,
            semantic_model=SemanticModel(**sem_model_data),
            starter_questions=questions,
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    @classmethod
    def update_semantic(
        cls,
        dataset_id: str,
        req: UpdateDatasetSemanticRequest,
        owner_token: Optional[str] = None
    ) -> DatasetSemanticResponse:
        """Allows owner to update measures, dimensions, synonyms, and confirm status."""
        current = cls.get_semantic(dataset_id, owner_token=owner_token)

        if req.status:
            if req.status not in ("draft", "confirmed"):
                raise FileValidationError("Status must be either 'draft' or 'confirmed'.", status_code=400)
            current.status = req.status

        if req.measures is not None:
            current.semantic_model.measures = req.measures
        if req.dimensions is not None:
            current.semantic_model.dimensions = req.dimensions
        if req.relationships is not None:
            current.semantic_model.relationships = req.relationships
        if req.starter_questions is not None:
            current.starter_questions = req.starter_questions
        if req.user_notes is not None:
            current.semantic_model.user_notes = req.user_notes

        current.updated_at = datetime.now(timezone.utc)

        if not is_fixture_mode():
            cls._save_to_db(current)

        return current
