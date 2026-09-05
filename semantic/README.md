# InsightForge — Semantic Layer Foundation

The **InsightForge Semantic Layer** provides a standardized, machine-readable repository of controlled business terms, metric calculations, analytical dimensions, and database join semantics for the InsightForge e-commerce analytics ecosystem.

---

## 📁 Directory Architecture

```
semantic/
├── business_glossary.yaml    # Controlled definitions for 19 core business terms and entities
├── metrics.yaml              # Machine-readable specifications for company KPIs (formulas, filters, grain)
├── dimensions.yaml           # Analytical dimensions catalog (tables, columns, allowed values)
├── relationships.yaml        # Schema join graph, entity cardinalities, and Cartesian fan-out safety rules
├── validate_semantic_layer.py# Automated semantic validator verifying schema cross-references & integrity
├── test_semantic_layer.py    # PyUnit test suite asserting semantic layer loader correctness
└── README.md                 # Semantic layer specification & developer documentation
```

---

## 🚀 Purpose & Role in InsightForge

1. **Single Source of Truth**: Resolves ambiguity between natural language business terminology (e.g. "sales", "top line", "CSAT") and PostgreSQL schema objects.
2. **Fan-Out Prevention**: Encapsulates mandatory join rules to prevent Cartesian row multiplication when aggregating financial metrics across multi-table relationships.
3. **Machine-Readable Metadata**: Uses standardized YAML format so that future Text-to-SQL drivers, RAG engines, and autonomous AI agents can seamlessly parse context without manual hardcoding.

---

## 🧪 Validation & Testing

Run the automated semantic validator:
```bash
python3 semantic/validate_semantic_layer.py
```

Run the unit test suite:
```bash
python3 semantic/test_semantic_layer.py
```

Run database analytics regression tests:
```bash
python3 database/test_analytics.py
```
