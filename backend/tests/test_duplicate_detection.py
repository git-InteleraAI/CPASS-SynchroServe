"""Tests for duplicate detection engine (Phase 2).

Verifies matching rules, potential vs confirmed distinction, strict mobile-only constraint,
and preservation of candidate records.
"""

import pytest
from app.services.duplicate_detection import (
    RULES,
    detect_duplicates_for_candidates,
    normalize_mobile,
    normalize_text,
    name_similarity,
)


def test_normalize_helpers():
    assert normalize_text("  Rahul   K.  Nair-Sharma ") == "rahul k nair sharma"
    assert normalize_mobile("+91 98765-43210") == "9876543210"
    assert normalize_mobile("09876543210") == "9876543210"
    assert normalize_mobile("0000000000") is None
    assert normalize_mobile("123") is None


def test_name_similarity():
    assert name_similarity("mohammad khan", "mohammed khan") > 0.85
    assert name_similarity("rahul sharma", "anita singh") < 0.35


def test_name_and_dob_rule():
    candidates = [
        {"candidate_id": 101, "first_name": "Rahul", "last_name": "Kumar", "dob": "1997-04-12", "mobile": "9999911111", "tc_id": 1},
        {"candidate_id": 102, "first_name": "rahul", "last_name": "kumar", "dob": "1997-04-12", "mobile": "8888822222", "tc_id": 1},
    ]
    matches = detect_duplicates_for_candidates(candidates)
    assert len(matches) == 1
    m = matches[0]
    assert m.rule_code == "NAME_DOB"
    assert m.candidate_id_a == 101
    assert m.candidate_id_b == 102
    assert m.severity == "POTENTIAL"


def test_name_dob_and_father_rule():
    candidates = [
        {"candidate_id": 201, "first_name": "Anita", "last_name": "Singh", "father_name": "Rajesh Singh", "dob": "1999-08-20", "tc_id": 2},
        {"candidate_id": 202, "first_name": "Anita", "last_name": "Singh", "father_name": "rajesh singh", "dob": "1999-08-20", "tc_id": 2},
    ]
    matches = detect_duplicates_for_candidates(candidates)
    assert len(matches) == 1
    m = matches[0]
    assert m.rule_code == "NAME_DOB_FATHER"
    assert m.confidence == "HIGH"


def test_shared_mobile_alone_is_strictly_potential():
    """Matching a mobile number alone must never identify two candidates as the same person."""
    candidates = [
        {"candidate_id": 301, "first_name": "Vikram", "last_name": "Joshi", "dob": "1995-01-01", "mobile": "9876543210", "tc_id": 3},
        {"candidate_id": 302, "first_name": "Deepa", "last_name": "Menon", "dob": "2000-11-15", "mobile": "+91-9876543210", "tc_id": 4},
    ]
    matches = detect_duplicates_for_candidates(candidates)
    assert len(matches) == 1
    m = matches[0]
    assert m.rule_code == "SHARED_MOBILE"
    assert m.severity == "POTENTIAL"
    assert m.confidence == "LOW"

    # Verify rule definition guarantees cannot auto-confirm
    rule_def = RULES["SHARED_MOBILE"]
    assert rule_def.can_auto_confirm is False
    assert rule_def.is_mobile_only is True
    assert "Must NOT identify candidates as the same person" in rule_def.rule_description


def test_similar_name_and_dob_rule():
    candidates = [
        {"candidate_id": 401, "first_name": "Mohammad", "last_name": "Tariq", "dob": "1996-03-25", "tc_id": 5},
        {"candidate_id": 402, "first_name": "Mohammed", "last_name": "Tariq", "dob": "1996-03-25", "tc_id": 5},
    ]
    matches = detect_duplicates_for_candidates(candidates)
    assert len(matches) == 1
    m = matches[0]
    assert m.rule_code == "SIMILAR_NAME_DOB"
    assert m.match_metadata["similarity"] >= 0.85


def test_conflicting_unique_identifier():
    candidates = [
        {"candidate_id": 501, "first_name": "Amit", "last_name": "Roy", "dob": "1998-05-10", "raw": {"KaushalPanjee_ID": "KP-9999"}},
        {"candidate_id": 502, "first_name": "Pooja", "last_name": "Devi", "dob": "2001-09-12", "raw": {"KaushalPanjee_ID": "KP-9999"}},
    ]
    matches = detect_duplicates_for_candidates(candidates)
    assert len(matches) == 1
    m = matches[0]
    assert m.rule_code == "CONFLICTING_IDENTIFIER"
    assert m.severity == "CRITICAL"


def test_candidate_records_are_never_mutated():
    candidates = [
        {"candidate_id": 601, "first_name": "Sameer", "last_name": "Khan", "dob": "1997-07-07"},
        {"candidate_id": 602, "first_name": "Sameer", "last_name": "Khan", "dob": "1997-07-07"},
    ]
    original_copy = [dict(c) for c in candidates]
    matches = detect_duplicates_for_candidates(candidates)

    assert len(matches) == 1
    # Both candidates preserved
    assert len(candidates) == 2
    assert candidates == original_copy
    assert candidates[0]["candidate_id"] == 601
    assert candidates[1]["candidate_id"] == 602
