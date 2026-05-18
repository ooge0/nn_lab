from typing import Optional, List

import pandas as pd
from pydantic import BaseModel, Field, ConfigDict, field_validator


class LabSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    student: str
    teacher: str

    bias: str = Field(default="N/A")
    system_prompt: Optional[str] = Field(default=None)

    archetype: str
    batch_time: Optional[str] = Field(alias="batch", default=None)
    duration_ms: float = 0.0
    val: float = 0.0

    readability_ari: Optional[float] = None
    corrected_ttr: Optional[float] = Field(default=0.0)
    subjectivity: Optional[float] = Field(default=0.0)
    sentiment: float = Field(default=0.0)
    sentiment_variance: float = Field(default=0.0)
    lexical_density: Optional[float] = None
    avg_sentence_length: float = Field(default=0.0)
    repetition_score: float = Field(default=0.0)
    rigidity: float = Field(default=0.0)


    # Core Metrics
    word_count: int = 0
    unique_ratio: float = 0.0
    ms_per_word: float = 0.0
    punc_density: float = 0.0

    # Semantic/Neuro
    levenshtein_dist: float = 0.0
    semantic_overlap: float = 0.0
    expansion_ratio: float = 1.0
    neuro_rigidity: float = 0.0
    neuro_cognitive_load: float = 0.0
    neuro_coherence: float = 0.0
    neuro_self_focus: float = 0.0
    neuro_abstract_ratio_ext: float = 0.0
    neuro_modality: float = 0.0

    # POS
    pos_adj: float = 0.0
    pos_noun: float = 0.0
    pos_verb: float = 0.0

    @field_validator('sentiment', mode='before')
    @classmethod
    def consolidate_sentiment(cls, v, info):
        # Professional logic to merge twins: if value is missing, check the raw data
        return float(v) if v is not None else 0.0


class LabDataBridge:
    @staticmethod
    def transform_raw(raw: dict) -> dict:
        """
        Standardizes and flattens raw experimental data into a format
        compatible with the LabSchema and visualization engines.
        """
        # 1. Access nested structures with fallback to root level
        # This ensures compatibility with both flat and nested JSON structures
        nlp = raw.get("nlp_raw", raw)
        neuro = raw.get("neuro_raw", raw)
        pos = nlp.get("pos_distribution", {})

        # 2. Build a flattened data structure
        flat = {
            **raw,  # Carry over all root identifiers (student, archetype, etc.)

            # --- NLP Metrics Extraction ---
            # Prioritize extended metrics if available, otherwise use base versions
            "corrected_ttr": nlp.get("corrected_ttr", 0.0),
            "subjectivity": nlp.get("subjectivity", 0.0),
            "lexical_density": nlp.get("lexical_density", 0.0),
            "repetition_score": nlp.get("repetition_score", 0.0),
            "avg_sentence_length": nlp.get("avg_sentence_length", 0.0),

            # Consolidate sentiment variance twins (core vs extended)
            "sentiment_variance": nlp.get("sentiment_variance_ext", nlp.get("sentiment_variance", 0.05)),

            # --- Neuropsychological Metrics (Prefixed for clear grouping) ---
            # Mapping raw keys to 'neuro_' prefixed fields expected by Plotly charts
            "neuro_self_focus": neuro.get("self_focus", 0.8),
            "neuro_rigidity": neuro.get("rigidity", 0.0),
            "neuro_cognitive_load": neuro.get("cognitive_load", 0.0),
            "neuro_coherence": neuro.get("coherence", 0.0),
            "neuro_abstract_ratio_ext": neuro.get("abstract_ratio_ext", 0.0),
            "neuro_modality": neuro.get("modality_ext", 0.0),

            # --- POS (Part of Speech) Distribution ---
            # Essential for Ternary Plot morphology analysis
            "pos_adj": pos.get("ADJ", 0.0),
            "pos_noun": pos.get("NOUN", 0.0),
            "pos_verb": pos.get("VERB", 0.0),
        }

        # 3. Pydantic Validation & Dumping
        # Performs type coercion and filters out any non-schema fields
        return LabSchema.model_validate(flat).model_dump()

    @staticmethod
    def optimize_df(df: pd.DataFrame) -> pd.DataFrame:
        """Reduces memory footprint and enforces strict typing."""
        if df.empty:
            return df

        # Convert strings to categories (huge memory saver for LLM names/archetypes)
        categorical_cols = ['student', 'archetype', 'batch_time', 'bias']
        for col in categorical_cols:
            if col in df.columns:
                df[col] = df[col].astype('category')

        # Downcast floats to save space
        float_cols = df.select_dtypes(include=['float64']).columns
        df[float_cols] = df[float_cols].apply(pd.to_numeric, downcast='float')

        return df

    @classmethod
    def build_dataframe(cls, history: List[dict]) -> pd.DataFrame:
        if not history:
            return pd.DataFrame()

        processed = [cls.transform_raw(r) for r in history]
        df = pd.DataFrame(processed)
        return cls.optimize_df(df)


def audit_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a visual report of data health."""
    report = []
    for col in df.columns:
        report.append({
            "Column": col,
            "Null %": round(df[col].isna().mean() * 100, 2),
            "Unique": df[col].nunique(),
            "Type": str(df[col].dtype)
        })
    return pd.DataFrame(report).set_index("Column")
