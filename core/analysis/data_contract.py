"""
data_contract.py

``LabSchema`` -- the standardized, validated shape a raw persisted response is normalized into
(every field defaulted, so a partial/legacy entry never crashes downstream code). ``LabDataBridge``
transforms a raw response dict into that schema and builds the resulting DataFrame -- the data path
:mod:`api.routers.nlp` uses (as opposed to the plain ``pandas.json_normalize`` most other routers
use directly over raw responses).
"""

from typing import Optional, List

import pandas as pd
from pydantic import BaseModel, Field, ConfigDict, field_validator


class LabSchema(BaseModel):
    """
    LabSchema defines the standardized structure for experimental lab data,
    including linguistic, neuropsychological, and semantic metrics.

    Main Description
    ----------------
    This schema ensures consistent validation and serialization of raw data
    into a format suitable for downstream visualization and analysis. It
    captures metrics such as readability, lexical diversity, sentiment,
    neurocognitive load, and part-of-speech distributions.

    References
    ----------
    - Pydantic BaseModel: https://docs.pydantic.dev/latest/usage/models/
    - Field configuration: https://docs.pydantic.dev/latest/concepts/fields/
    - Automated Readability Index (ARI): https://en.wikipedia.org/wiki/Automated_readability_index
    - Lexical density: https://en.wikipedia.org/wiki/Lexical_density
    - Sentiment analysis: https://en.wikipedia.org/wiki/Sentiment_analysis
    - POS tagging (Universal Dependencies): https://universaldependencies.org/u/pos/

    Required Params
    ---------------
    student : str
        Identifier for the student participant.
    teacher : str
        Identifier for the teacher or evaluator.
    bias : str, optional
        Bias label (default "N/A").
    system_prompt : str, optional
        System prompt used in the experiment.
    archetype : str
        Archetype label for clustering/grouping.
    batch_time : str, optional
        Batch timestamp (alias: "batch").
    duration_ms : float
        Duration of the experiment in milliseconds.
    val : float
        General-purpose numeric value (e.g., score).
    readability_ari : float, optional
        Automated Readability Index score.
    corrected_ttr : float, optional
        Corrected Type-Token Ratio (lexical diversity).
    subjectivity : float, optional
        Subjectivity score of text.
    sentiment : float
        Sentiment polarity score.
    sentiment_variance : float
        Variance in sentiment across text segments.
    lexical_density : float, optional
        Ratio of lexical words to total words.
    avg_sentence_length : float
        Average sentence length in words.
    repetition_score : float
        Measure of redundancy in text.
    rigidity : float
        Measure of structural rigidity in responses.
    word_count : int
        Total word count.
    unique_ratio : float
        Ratio of unique words to total words.
    ms_per_word : float
        Average milliseconds per word.
    punc_density : float
        Density of punctuation marks.
    levenshtein_dist : float
        Edit distance metric for similarity.
    semantic_overlap : float
        Overlap of semantic content across responses.
    expansion_ratio : float
        Ratio of expanded content relative to baseline.
    neuro_rigidity : float
        Neuropsychological rigidity score.
    neuro_cognitive_load : float
        Cognitive load estimate.
    neuro_coherence : float
        Coherence score.
    neuro_self_focus : float
        Self-focus metric.
    neuro_abstract_ratio_ext : float
        Abstractness ratio (extended).
    neuro_modality : float
        Modality distribution score.
    pos_adj : float
        Adjective proportion in POS distribution.
    pos_noun : float
        Noun proportion in POS distribution.
    pos_verb : float
        Verb proportion in POS distribution.

    Other Staff
    -----------
    - Supports aliasing (`batch` → `batch_time`) via ConfigDict.
    - Extra fields in raw input are ignored (`extra='ignore'`).
    - Sentiment is coerced to float via validator.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

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

    @field_validator("sentiment", mode="before")
    @classmethod
    def consolidate_sentiment(cls, v):
        """
        Consolidates sentiment values by coercing to float.

        Parameters
        ----------
        v : Any
            Raw sentiment value.

        Returns
        -------
        float
            Sentiment value coerced to float, defaults to 0.0 if missing.
        """
        return float(v) if v is not None else 0.0


class LabDataBridge:
    """
    LabDataBridge provides utilities to transform raw experimental data
    into validated LabSchema objects and optimized DataFrames.

    Responsibilities:
    - Flatten nested JSON structures into schema-compatible dicts.
    - Enforce strict typing and memory optimization in DataFrames.
    - Provide convenience methods for building datasets from history logs.

    References
    ----------
    - pandas DataFrame optimization: https://pandas.pydata.org/docs/user_guide/scale.html
    - Pydantic validation: https://docs.pydantic.dev/latest/usage/validation/
    - POS tagging: https://universaldependencies.org/u/pos/
    """

    @staticmethod
    def transform_raw(raw: dict) -> dict:
        """
        Standardizes and flattens raw experimental data into LabSchema format.

        Parameters
        ----------
        raw : dict
            Raw JSON-like dictionary containing NLP, neuro, and POS metrics.

        Returns
        -------
        dict
            Flattened and validated dictionary compatible with LabSchema.

        Notes
        -----
        - Nested structures (nlp_raw, neuro_raw) are supported.
        - Sentiment variance twins are consolidated.
        - Neuro metrics are prefixed with ``neuro_`` for clarity.
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
            # Mapping raw keys to 'neuro_' prefixed fields expected by Plotly charts.
            # self_focus_ext prioritized over self_focus, mirroring the same
            # extended-over-base convention already used above for
            # sentiment_variance -- ExperimentRunner (Stage 6) started persisting
            # self_focus (PsychScientist, broad pronoun set) and self_focus_ext
            # (NeuroMetrics, narrower set) as two separate keys, where this
            # mapping previously assumed only one "self_focus" key existed and
            # would always be NeuroMetrics' value (true only for pre-Stage-6
            # exports, where the legacy dict-merge collision happened to let
            # neuro's value win under the unprefixed key). On current data this
            # silently mislabeled PsychScientist's value as "neuro_self_focus".
            # Falls back to the bare key for historical exports that predate the
            # split.
            "neuro_self_focus": neuro.get("self_focus_ext", neuro.get("self_focus", 0.8)),
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
        """
        Optimize DataFrame memory usage and enforce strict typing.

        Parameters
        ----------
        df : pandas.DataFrame
            Input DataFrame.

        Returns
        -------
        pandas.DataFrame
            Optimized DataFrame with categorical and downcasted float columns.

        Notes
        -----
        - Converts string identifiers to categorical dtype.
        - Downcasts float64 to float32 for memory efficiency.
        """
        if df.empty:
            return df

        # Convert strings to categories (huge memory saver for LLM names/archetypes)
        categorical_cols = ["student", "archetype", "batch_time", "bias"]
        for col in categorical_cols:
            if col in df.columns:
                df[col] = df[col].astype("category")

        # Downcast floats to save space
        float_cols = df.select_dtypes(include=["float64"]).columns
        df[float_cols] = df[float_cols].apply(pd.to_numeric, downcast="float")

        return df

    @classmethod
    def build_dataframe(cls, history: List[dict]) -> pd.DataFrame:
        """
        Build a validated and optimized DataFrame from raw history logs.

        Parameters
        ----------
        history : list of dict
            List of raw experimental records.

        Returns
        -------
        pandas.DataFrame
            Optimized DataFrame containing validated LabSchema records.
        """
        if not history:
            return pd.DataFrame()

        processed = [cls.transform_raw(r) for r in history]
        df = pd.DataFrame(processed)
        return cls.optimize_df(df)


def audit_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a visual report of DataFrame column health.

    Parameters
    ----------
    df : pandas.DataFrame
        Input DataFrame.

    Returns
    -------
    pandas.DataFrame
        Report with columns:
        - Column: column name
        - Null %: percentage of missing values
        - Unique: number of unique values
        - Type: dtype of the column

    Notes
    -----
    Useful for quick diagnostics of schema compliance and data quality.
    """
    report = []
    for col in df.columns:
        report.append(
            {
                "Column": col,
                "Null %": round(df[col].isna().mean() * 100, 2),
                "Unique": df[col].nunique(),
                "Type": str(df[col].dtype),
            }
        )
    return pd.DataFrame(report).set_index("Column")
