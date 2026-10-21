"""Duplicate candidate detection service for CPASS.

Detects possible duplicate candidates using configurable matching rules.
Preserves every candidate record and Candidate_ID intact (never merges or deletes).
Distinguishes potential duplicates from confirmed duplicates.
A shared mobile number alone is strictly categorized as POTENTIAL and must never
identify candidates as the same person without independent corroboration.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
from typing import Any


@dataclass
class MatchingRuleConfig:
    rule_code: str
    rule_description: str
    severity: str = "POTENTIAL"  # "POTENTIAL" | "CRITICAL"
    confidence: str = "MEDIUM"   # "LOW" | "MEDIUM" | "HIGH"
    can_auto_confirm: bool = False
    is_mobile_only: bool = False
    similarity_threshold: float = 0.85


RULES: dict[str, MatchingRuleConfig] = {
    "NAME_DOB": MatchingRuleConfig(
        rule_code="NAME_DOB",
        rule_description="Exact match on normalized candidate name and date of birth.",
        severity="POTENTIAL",
        confidence="HIGH",
    ),
    "NAME_DOB_FATHER": MatchingRuleConfig(
        rule_code="NAME_DOB_FATHER",
        rule_description="Exact match on candidate name, date of birth, and father's name.",
        severity="POTENTIAL",
        confidence="HIGH",
    ),
    "SHARED_MOBILE": MatchingRuleConfig(
        rule_code="SHARED_MOBILE",
        rule_description="Shared normalized 10-digit mobile number. Must NOT identify candidates as the same person.",
        severity="POTENTIAL",
        confidence="LOW",
        can_auto_confirm=False,
        is_mobile_only=True,
    ),
    "SIMILAR_NAME_DOB": MatchingRuleConfig(
        rule_code="SIMILAR_NAME_DOB",
        rule_description="High string similarity on candidate name with exact date of birth.",
        severity="POTENTIAL",
        confidence="MEDIUM",
        similarity_threshold=0.85,
    ),
    "CONFLICTING_IDENTIFIER": MatchingRuleConfig(
        rule_code="CONFLICTING_IDENTIFIER",
        rule_description="Conflicting records sharing an identifier that should be unique (e.g. Candidate_ID or KaushalPanjee_ID).",
        severity="CRITICAL",
        confidence="HIGH",
    ),
}


@dataclass
class CandidateDuplicateMatch:
    candidate_id_a: int
    candidate_id_b: int
    rule_code: str
    rule_description: str
    severity: str
    confidence: str
    match_metadata: dict[str, Any] = field(default_factory=dict)
    tc_id: int | None = None


def normalize_text(val: Any) -> str:
    """Normalize text by stripping, lowercasing, and collapsing whitespace and punctuation."""
    if val is None:
        return ""
    s = str(val).lower().strip()
    # Replace dots, commas, hyphens with space
    s = re.sub(r"[.,\-_\/]", " ", s)
    # Collapse multiple whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_mobile(val: Any) -> str | None:
    """Extract standard 10-digit mobile number or return None if invalid."""
    if val is None:
        return None
    digits = re.sub(r"\D", "", str(val))
    # If prefixed by country code 91
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) == 10 and digits != "0000000000" and not digits.startswith("0"):
        return digits
    return None


def name_similarity(name_a: str, name_b: str) -> float:
    """Calculate normalized string similarity ratio between two names."""
    if not name_a or not name_b:
        return 0.0
    if name_a == name_b:
        return 1.0
    return SequenceMatcher(None, name_a, name_b).ratio()


def detect_duplicates_for_candidates(
    candidates: list[dict[str, Any]],
    enabled_rules: list[str] | None = None,
) -> list[CandidateDuplicateMatch]:
    """Analyze a list of candidate dictionaries and return detected duplicate matches.

    Never modifies candidate records.
    """
    if enabled_rules is None:
        active_rules = set(RULES.keys())
    else:
        active_rules = set(enabled_rules)

    matches: list[CandidateDuplicateMatch] = []
    seen_pairs: set[tuple[int, int, str]] = set()

    # Pre-process candidates with normalized keys
    normalized_list = []
    for c in candidates:
        cid = c.get("candidate_id")
        if cid is None:
            continue
        first = c.get("first_name") or ""
        last = c.get("last_name") or ""
        full_name = f"{first} {last}".strip()
        norm_name = normalize_text(full_name)
        norm_father = normalize_text(c.get("father_name"))
        norm_dob = c.get("dob") or ""
        norm_mob = normalize_mobile(c.get("mobile"))
        tc_id = c.get("tc_id")

        # Also inspect raw data for unique identifier conflicts if available
        raw = c.get("raw") or {}
        kp_id = normalize_text(raw.get("KaushalPanjee_ID"))

        normalized_list.append({
            "candidate_id": int(cid),
            "tc_id": tc_id,
            "full_name": full_name,
            "norm_name": norm_name,
            "norm_father": norm_father,
            "norm_dob": norm_dob,
            "norm_mob": norm_mob,
            "kp_id": kp_id,
        })

    total = len(normalized_list)

    # 1. Bucket by normalized DOB for fast Name + DOB comparison
    if "NAME_DOB" in active_rules or "NAME_DOB_FATHER" in active_rules or "SIMILAR_NAME_DOB" in active_rules:
        dob_buckets: dict[str, list[dict]] = {}
        for c in normalized_list:
            if c["norm_dob"]:
                dob_buckets.setdefault(c["norm_dob"], []).append(c)

        for dob_val, group in dob_buckets.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    c1, c2 = group[i], group[j]
                    id_a, id_b = min(c1["candidate_id"], c2["candidate_id"]), max(c1["candidate_id"], c2["candidate_id"])

                    # Rule: NAME_DOB_FATHER
                    if "NAME_DOB_FATHER" in active_rules and c1["norm_name"] and c1["norm_name"] == c2["norm_name"]:
                        if c1["norm_father"] and c1["norm_father"] == c2["norm_father"]:
                            pair_key = (id_a, id_b, "NAME_DOB_FATHER")
                            if pair_key not in seen_pairs:
                                seen_pairs.add(pair_key)
                                cfg = RULES["NAME_DOB_FATHER"]
                                matches.append(CandidateDuplicateMatch(
                                    candidate_id_a=id_a,
                                    candidate_id_b=id_b,
                                    rule_code=cfg.rule_code,
                                    rule_description=cfg.rule_description,
                                    severity=cfg.severity,
                                    confidence=cfg.confidence,
                                    match_metadata={
                                        "matched_dob": dob_val,
                                        "matched_name": c1["norm_name"],
                                        "matched_father": c1["norm_father"],
                                    },
                                    tc_id=c1["tc_id"] if c1["tc_id"] == c2["tc_id"] else None,
                                ))
                                continue  # Covered by stricter rule

                    # Rule: NAME_DOB
                    if "NAME_DOB" in active_rules and c1["norm_name"] and c1["norm_name"] == c2["norm_name"]:
                        pair_key = (id_a, id_b, "NAME_DOB")
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            cfg = RULES["NAME_DOB"]
                            matches.append(CandidateDuplicateMatch(
                                candidate_id_a=id_a,
                                candidate_id_b=id_b,
                                rule_code=cfg.rule_code,
                                rule_description=cfg.rule_description,
                                severity=cfg.severity,
                                confidence=cfg.confidence,
                                match_metadata={
                                    "matched_dob": dob_val,
                                    "matched_name": c1["norm_name"],
                                },
                                tc_id=c1["tc_id"] if c1["tc_id"] == c2["tc_id"] else None,
                            ))
                            continue

                    # Rule: SIMILAR_NAME_DOB
                    if "SIMILAR_NAME_DOB" in active_rules and c1["norm_name"] and c2["norm_name"]:
                        sim = name_similarity(c1["norm_name"], c2["norm_name"])
                        cfg = RULES["SIMILAR_NAME_DOB"]
                        if sim >= cfg.similarity_threshold and c1["norm_name"] != c2["norm_name"]:
                            pair_key = (id_a, id_b, "SIMILAR_NAME_DOB")
                            if pair_key not in seen_pairs:
                                seen_pairs.add(pair_key)
                                matches.append(CandidateDuplicateMatch(
                                    candidate_id_a=id_a,
                                    candidate_id_b=id_b,
                                    rule_code=cfg.rule_code,
                                    rule_description=cfg.rule_description,
                                    severity=cfg.severity,
                                    confidence=cfg.confidence,
                                    match_metadata={
                                        "matched_dob": dob_val,
                                        "similarity": round(sim, 3),
                                        "name_a": c1["norm_name"],
                                        "name_b": c2["norm_name"],
                                    },
                                    tc_id=c1["tc_id"] if c1["tc_id"] == c2["tc_id"] else None,
                                ))

    # 2. Bucket by normalized mobile number
    if "SHARED_MOBILE" in active_rules:
        mobile_buckets: dict[str, list[dict]] = {}
        for c in normalized_list:
            if c["norm_mob"]:
                mobile_buckets.setdefault(c["norm_mob"], []).append(c)

        for mob_val, group in mobile_buckets.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    c1, c2 = group[i], group[j]
                    id_a, id_b = min(c1["candidate_id"], c2["candidate_id"]), max(c1["candidate_id"], c2["candidate_id"])
                    pair_key = (id_a, id_b, "SHARED_MOBILE")
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        cfg = RULES["SHARED_MOBILE"]
                        matches.append(CandidateDuplicateMatch(
                            candidate_id_a=id_a,
                            candidate_id_b=id_b,
                            rule_code=cfg.rule_code,
                            rule_description=cfg.rule_description,
                            severity=cfg.severity,
                            confidence=cfg.confidence,
                            match_metadata={
                                "shared_mobile_suffix": mob_val[-4:],  # Mask sensitive number
                                "note": "Shared mobile alone is a potential duplicate only. Never auto-confirm.",
                            },
                            tc_id=c1["tc_id"] if c1["tc_id"] == c2["tc_id"] else None,
                        ))

    # 3. Bucket by unique external identifiers (e.g. KaushalPanjee_ID)
    if "CONFLICTING_IDENTIFIER" in active_rules:
        kp_buckets: dict[str, list[dict]] = {}
        for c in normalized_list:
            if c["kp_id"]:
                kp_buckets.setdefault(c["kp_id"], []).append(c)

        for kp_val, group in kp_buckets.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    c1, c2 = group[i], group[j]
                    id_a, id_b = min(c1["candidate_id"], c2["candidate_id"]), max(c1["candidate_id"], c2["candidate_id"])
                    # If same identifier has conflicting personal details
                    if c1["norm_name"] != c2["norm_name"] or c1["norm_dob"] != c2["norm_dob"]:
                        pair_key = (id_a, id_b, "CONFLICTING_IDENTIFIER")
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            cfg = RULES["CONFLICTING_IDENTIFIER"]
                            matches.append(CandidateDuplicateMatch(
                                candidate_id_a=id_a,
                                candidate_id_b=id_b,
                                rule_code=cfg.rule_code,
                                rule_description=cfg.rule_description,
                                severity=cfg.severity,
                                confidence=cfg.confidence,
                                match_metadata={
                                    "conflicting_identifier": "KaushalPanjee_ID",
                                    "reason": "Identical KaushalPanjee_ID with discrepant name or DOB.",
                                },
                                tc_id=c1["tc_id"] if c1["tc_id"] == c2["tc_id"] else None,
                            ))

    return matches
