"""
Unit tests for :mod:`core.analysis.response_classification` -- Layer 0 (deterministic response
classification) and Layer 1 (embedding-based echo detection) of the per-response evaluation
cascade (CLAUDE.md SS3a). See the module's own docstring for why Layer 1's threshold direction is
the opposite of the standard "low similarity means off-topic" STS intuition -- calibrated against
real generated data, not guessed, and pinned here on the same real examples that calibration used.
"""

from core.analysis.response_classification import ResponseClassification, classify_response, is_echo_response

# --- classify_response (Layer 0) -----------------------------------------


def test_classify_response_valid_json_with_text_key_is_valid():
    assert classify_response('{"text": "a real generated response"}') == ResponseClassification.VALID


def test_classify_response_empty_string_is_empty():
    assert classify_response("") == ResponseClassification.EMPTY
    assert classify_response("   ") == ResponseClassification.EMPTY


def test_classify_response_valid_json_with_empty_text_value_is_empty():
    """The JSON structure is fine, but the actual text content is blank -- still nothing to judge."""
    assert classify_response('{"text": ""}') == ResponseClassification.EMPTY
    assert classify_response('{"text": "   "}') == ResponseClassification.EMPTY


def test_classify_response_valid_json_missing_text_key_is_schema_error():
    assert classify_response('{"result": "wrong key entirely"}') == ResponseClassification.SCHEMA_ERROR


def test_classify_response_valid_json_but_not_an_object_is_schema_error():
    """A JSON array or bare string is syntactically valid JSON but not the expected {"text": ...} shape."""
    assert classify_response('["not", "an", "object"]') == ResponseClassification.SCHEMA_ERROR
    assert classify_response('"just a string"') == ResponseClassification.SCHEMA_ERROR


def test_classify_response_cut_off_mid_json_is_truncated():
    """Unbalanced braces/quotes -- the classic shape of a response that hit a token limit mid-generation, not one that was garbled from the start."""
    assert classify_response('{"text": "the model was cut off mid-sen') == ResponseClassification.TRUNCATED


def test_classify_response_genuinely_garbled_non_json_is_malformed():
    """Complete, well-formed-looking prose that just isn't JSON at all -- ends on a normal sentence boundary, braces balanced (zero of each), so it doesn't look cut off."""
    assert (
        classify_response("The model ignored the JSON instruction entirely.") == ResponseClassification.MALFORMED_JSON
    )


# --- is_echo_response (Layer 1) -------------------------------------------
#
# Thresholds pinned on the real semantic_overlap values found calibrating this check against
# results/lab_experiment_results/*.jsonl (see response_classification.py's own comment for the
# full real-data cause-and-effect story) -- not arbitrary numbers.


def test_is_echo_response_true_for_real_confirmed_echo_scores():
    """Real echo failures observed in this project's own generated data scored 0.59 and 0.98 -- both must be flagged."""
    assert is_echo_response(0.59) is True
    assert is_echo_response(0.98) is True


def test_is_echo_response_false_for_real_genuine_response_scores():
    """Real genuine, substantive responses observed in this project's own generated data scored between 0.06 and 0.30 -- none of these should be flagged as echoes."""
    for score in [0.06, 0.09, 0.14, 0.16, 0.21, 0.30]:
        assert is_echo_response(score) is False


def test_is_echo_response_boundary_at_exactly_the_threshold():
    """Exactly at the threshold is not flagged -- only strictly above it is, matching the real data's clean gap sitting well past 0.5 on the echo side."""
    assert is_echo_response(0.5) is False
    assert is_echo_response(0.501) is True
