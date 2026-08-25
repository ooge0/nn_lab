import pytest

from core.analysis.data_contract import LabDataBridge, LabSchema

# --- FIXTURES & HELPERS ---


def sample_row_data():
    """
    Generate a sample dictionary mimicking the synthetic dataset structure.
    Note: self_focus (top-level, PsychScientist's value) and neuro_raw's
    self_focus_ext (NeuroMetrics' value) are deliberately different (0.8 vs
    0.3) so tests can confirm the Bridge doesn't conflate the two.
    """
    return {
        "student": "qwen:latest",
        "teacher": "llama3:latest",
        "archetype": "Structured",
        "word_count": 259,
        "unique_ratio": 0.68,
        "ms_per_word": 145.32,
        "punc_density": 0.16,
        "levenshtein_dist": 1747,
        "semantic_overlap": 0.0,
        "expansion_ratio": 259.0,
        "duration_ms": 37637.43,
        "sentiment": 0.986,
        "readability_ari": 11.97,
        "self_focus": 0.8,
        "rigidity": 0.569,
        "nlp_raw": {
            "sentiment": 0.986,
            "readability_ari": 11.97,
            "word_count": 248,
            "pos_distribution": {"NOUN": 0.2, "VERB": 0.1, "ADJ": 0.4},
        },
        "neuro_raw": {
            "rigidity": 0.4,
            "coherence": 0.02,
            "sentiment_variance_ext": 0.05,
            "corrected_ttr": 1.225,
            "self_focus_ext": 0.3,
        },
    }


@pytest.fixture
def sample_df():
    """Pytest fixture to provide a pre-built DataFrame for testing."""
    return LabDataBridge.build_dataframe([sample_row_data()])


# --- ALIGNMENT TESTS ---


def test_full_pipeline_alignment():
    """
    Ensures raw JSON data correctly flows through the Bridge into the Schema
    and finally into a DataFrame with the exact keys required by Plotly.
    """
    raw_sample = sample_row_data()

    # Act
    transformed = LabDataBridge.transform_raw(raw_sample)
    df = LabDataBridge.build_dataframe([raw_sample])

    # Assert: Verify 'Teacher' exists (your new addition)
    assert transformed["teacher"] == "llama3:latest"

    # Assert: neuro_self_focus comes from NeuroMetrics' self_focus_ext (0.3),
    # not the top-level PsychScientist self_focus (0.8) -- they're deliberately
    # different values in the fixture so this can't pass by accident.
    assert transformed["neuro_self_focus"] == 0.3
    assert transformed["pos_adj"] == 0.4

    # Assert: Verify sentiment_variance consolidation
    assert transformed["sentiment_variance"] == 0.05

    # Assert: Ensure Plotly columns exist in the resulting DataFrame
    expected_cols = ["student", "teacher", "neuro_self_focus", "pos_adj", "corrected_ttr"]
    for col in expected_cols:
        assert col in df.columns, f"Visualization column {col} missing from DataFrame!"


def test_alias_regression_check():
    """
    Verify that providing 'neuro_self_focus' directly works
    and isn't ignored in favor of an old 'self_focus' alias.
    """
    # Fix: Add mandatory fields required by LabSchema
    data = {
        "student": "test_bot",
        "teacher": "test_judge",
        "archetype": "Detached",
        "neuro_self_focus": 0.99,
        "self_focus": 0.00,
    }
    validated = LabSchema.model_validate(data).model_dump()

    # This will now reach the assertion
    assert validated["neuro_self_focus"] == 0.99


def test_neuro_self_focus_prefers_ext_over_base_on_a_flat_stage6_style_entry():
    """
    Regression test for a real bug: ExperimentRunner (Stage 6) persists real
    entries *flat*, not nested under nlp_raw/neuro_raw (confirmed against a
    live-generated JSONL entry, not assumed) -- with self_focus
    (PsychScientist, broad pronoun set) and self_focus_ext (NeuroMetrics,
    narrower set) as two separate top-level keys. transform_raw's
    neuro_self_focus mapping previously read the bare "self_focus" key
    unconditionally, silently mislabeling PsychScientist's value as
    NeuroMetrics' on every real, current entry. Must prefer self_focus_ext.
    """
    flat_entry = {
        "student": "qwen:latest",
        "teacher": "llama3:latest",
        "archetype": "Detached",
        "self_focus": 0.8,  # PsychScientist's value -- must NOT win
        "self_focus_ext": 0.3,  # NeuroMetrics' value -- must win
    }

    transformed = LabDataBridge.transform_raw(flat_entry)

    # LabSchema doesn't declare a plain "self_focus" field (extra="ignore" drops
    # it) -- only the prefixed neuro_self_focus is part of the curated schema.
    assert transformed["neuro_self_focus"] == 0.3
    assert "self_focus" not in transformed


def test_neuro_self_focus_falls_back_to_bare_key_for_pre_stage6_entries():
    """A flat entry with only the old-style bare 'self_focus' key (no _ext) still resolves -- historical exports aren't left broken."""
    flat_entry = {
        "student": "qwen:latest",
        "teacher": "llama3:latest",
        "archetype": "Detached",
        "self_focus": 0.55,
    }

    transformed = LabDataBridge.transform_raw(flat_entry)

    assert transformed["neuro_self_focus"] == 0.55


# --- SUITE FOR REFACTORED FEATURES ---


class TestNlpProjectFeature:
    """Suite of tests for validating the refactored NLP data contract logic."""

    def test_schema_parsing(self):
        """Validate that LabSchema can parse the flattened data correctly."""
        data = LabDataBridge.transform_raw(sample_row_data())
        obj = LabSchema.model_validate(data)
        assert obj.word_count == 259
        assert obj.teacher == "llama3:latest"

    def test_dataframe_build(self, sample_df):
        """Ensure the build_dataframe function creates columns and retains data."""
        assert "sentiment" in sample_df.columns
        assert "punc_density" in sample_df.columns
        assert sample_df.loc[0, "word_count"] == 259

    def test_no_nan_critical(self, sample_df):
        """Check for missing values in critical numeric columns."""
        critical_cols = ["sentiment", "ms_per_word", "punc_density", "neuro_rigidity"]
        for col in critical_cols:
            assert col in sample_df.columns
            assert sample_df[col].notna().all()

    def test_pos_mapping(self):
        """Verify the POS distribution is flattened correctly for Ternary plots."""
        data = sample_row_data()
        transformed = LabDataBridge.transform_raw(data)
        assert transformed["pos_adj"] == 0.4
        assert transformed["pos_noun"] == 0.2
        assert transformed["pos_verb"] == 0.1

    def test_neuro_fields_prefixed(self, sample_df):
        """Verify that psychological fields use the ``neuro_`` prefix in the DF."""
        assert "neuro_rigidity" in sample_df.columns
        # Ensure the old unprefixed name isn't cluttering the final DF if not in Schema
        # (This depends on whether you kept 'rigidity' in LabSchema or not)
