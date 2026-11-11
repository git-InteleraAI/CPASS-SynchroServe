"""Service module for state-wise semi-skilled minimum wage lookups and validation.

Performs authoritative lookups against the Supabase `min_wages` master table
using the effective date rule:
    effective_date <= selected_salary_period
ordered by effective_date DESC limit 1.
"""

from __future__ import annotations

import logging
from typing import Any

from postgrest.exceptions import APIError

from ..auth import get_candidate_state, resolve_state
from ..db import TRANSIENT_ERRORS, retry_read_query, supabase
from .location_detector import LocationDetectionResult, detect_work_state

logger = logging.getLogger("cpass.min_wages")


def lookup_minimum_wage_for_date(state: str, date_str: str) -> dict[str, Any] | None:
    """Fetch the latest applicable semi-skilled minimum wage revision for a state on or before a date.

    Rule: effective_date <= date_str (YYYY-MM-DD or YYYY-MM), ordered by effective_date DESC limit 1.
    """
    canon_state = resolve_state(state)
    if not canon_state:
        logger.warning("Cannot resolve canonical state for minimum wage lookup: %r", state)
        return None

    if not date_str:
        return None

    target_date = date_str[:10]
    if len(target_date) == 7:  # YYYY-MM
        target_date = f"{target_date}-01"

    try:
        res = retry_read_query(
            lambda: supabase.table("min_wages")
            .select("id,state,month,year,effective_date,skill_category,minimum_wage,source")
            .eq("state", canon_state)
            .eq("skill_category", "SEMI-SKILLED")
            .lte("effective_date", target_date)
            .order("effective_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows:
            row = rows[0]
            return {
                "state": row.get("state", canon_state),
                "skill_category": row.get("skill_category", "SEMI-SKILLED"),
                "minimum_wage": float(row["minimum_wage"]),
                "effective_month": int(row["month"]),
                "effective_year": int(row["year"]),
                "effective_date": str(row["effective_date"]),
                "source": row.get("source"),
            }
        return None
    except APIError as exc:
        logger.error("Database error querying min_wages for %s on %s: %s", canon_state, target_date, exc)
        raise
    except TRANSIENT_ERRORS:
        raise
    except Exception as exc:
        logger.exception("Unexpected error querying min_wages for %s on %s: %s", canon_state, target_date, exc)
        raise


def lookup_minimum_wage_for_period(state: str, month: int, year: int) -> dict[str, Any] | None:
    """Fetch the latest applicable semi-skilled minimum wage revision for a state and period.

    Rule: effective_date <= YYYY-MM-01, ordered by effective_date DESC limit 1.
    """
    canon_state = resolve_state(state)
    if not canon_state:
        logger.warning("Cannot resolve canonical state for minimum wage lookup: %r", state)
        return None

    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}. Month must be between 1 and 12.")
    if year < 2000 or year > 2050:
        raise ValueError(f"Invalid year: {year}. Year must be between 2000 and 2050.")

    target_date = f"{year:04d}-{month:02d}-01"

    try:
        res = retry_read_query(
            lambda: supabase.table("min_wages")
            .select("id,state,month,year,effective_date,skill_category,minimum_wage,source")
            .eq("state", canon_state)
            .eq("skill_category", "SEMI-SKILLED")
            .lte("effective_date", target_date)
            .order("effective_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows:
            row = rows[0]
            return {
                "state": row.get("state", canon_state),
                "skill_category": row.get("skill_category", "SEMI-SKILLED"),
                "requested_month": month,
                "requested_year": year,
                "minimum_wage": float(row["minimum_wage"]),
                "effective_month": int(row["month"]),
                "effective_year": int(row["year"]),
                "effective_date": str(row["effective_date"]),
                "source": row.get("source"),
            }
        return None
    except APIError as exc:
        logger.error("Database error querying min_wages for %s on %s: %s", canon_state, target_date, exc)
        raise
    except TRANSIENT_ERRORS:
        raise
    except Exception as exc:
        logger.exception("Unexpected error querying min_wages for %s on %s: %s", canon_state, target_date, exc)
        raise


def apply_authoritative_employer_and_salary_wages(
    candidate: dict[str, Any],
    employer_entries: list[dict[str, Any]],
    salary_entries: list[dict[str, Any]],
    strict: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Enrich employers with detected work_state & appointment minimum wage, and enrich salary rows
    using their associated employer's detected work state.

    Never substitutes candidate beneficiary state if employer location is missing or unsupported.
    """
    enriched_employers: list[dict[str, Any]] = []
    emp_state_map: dict[str, str] = {}
    emp_status_map: dict[str, str] = {}

    for emp in employer_entries:
        emp_copy = dict(emp)
        emp_id = str(emp_copy.get("id") or emp_copy.get("employer_id") or "")
        place = emp_copy.get("place_of_work")

        if place:
            det: LocationDetectionResult = detect_work_state(place)
            emp_copy["work_state"] = det.detected_state
            emp_copy["work_state_detection_status"] = det.status

            if det.status == "IDENTIFIED" and det.detected_state:
                emp_state_map[emp_id] = det.detected_state
                emp_status_map[emp_id] = "IDENTIFIED"
                appt_date = emp_copy.get("appointment_date")
                if appt_date:
                    try:
                        wage_info = lookup_minimum_wage_for_date(det.detected_state, appt_date)
                        if wage_info:
                            emp_copy["minimum_wages"] = wage_info["minimum_wage"]
                            emp_copy["minimum_wages_effective_month"] = wage_info["effective_month"]
                            emp_copy["minimum_wages_effective_year"] = wage_info["effective_year"]
                        else:
                            emp_copy["minimum_wages"] = None
                    except Exception as exc:
                        logger.warning("Failed to lookup minimum wage for employer %s (%s, %s): %s", emp_id, det.detected_state, appt_date, exc)
                        emp_copy["minimum_wages"] = None
                else:
                    emp_copy["minimum_wages"] = None
            else:
                emp_status_map[emp_id] = det.status
                emp_copy["minimum_wages"] = None
                if strict and det.status == "UNSUPPORTED_STATE":
                    raise ValueError(
                        f"Employer '{emp_copy.get('employer_name')}' place of work is in '{det.detected_state}', which is not supported in the 13-state minimum wage register."
                    )
                elif strict and det.status == "AMBIGUOUS":
                    raise ValueError(
                        f"Employer '{emp_copy.get('employer_name')}' place of work '{place}' is ambiguous ({', '.join(det.candidate_states)}). Please specify state or district."
                    )
        else:
            # If employer has pre-existing work_state, preserve it
            if emp_copy.get("work_state"):
                canon = resolve_state(emp_copy["work_state"])
                if canon:
                    emp_state_map[emp_id] = canon
                    emp_status_map[emp_id] = "IDENTIFIED"
            else:
                # Legacy fallback for historical audits without place_of_work
                cand_state = get_candidate_state(candidate)
                if cand_state:
                    emp_state_map[emp_id] = cand_state
                    emp_status_map[emp_id] = "LEGACY_FALLBACK"

        enriched_employers.append(emp_copy)

    # If only 1 employer exists, map fallback
    single_emp_state = None
    if len(enriched_employers) == 1 and enriched_employers[0].get("work_state"):
        single_emp_state = enriched_employers[0]["work_state"]

    enriched_salaries: list[dict[str, Any]] = []
    for sal in salary_entries:
        sal_copy = dict(sal)
        sal_emp_id = str(sal_copy.get("employer_id") or "")
        
        # State resolution: associated employer's work_state
        sal_work_state = emp_state_map.get(sal_emp_id) or single_emp_state
        sal_emp_status = emp_status_map.get(sal_emp_id)

        m = sal_copy.get("month")
        y = sal_copy.get("year")

        if m and y:
            try:
                m_int = int(m)
                y_int = int(y)

                if sal_work_state:
                    wage_info = lookup_minimum_wage_for_period(sal_work_state, m_int, y_int)
                    if wage_info:
                        sal_copy["minimum_wage"] = wage_info["minimum_wage"]
                        sal_copy["minimum_wage_state"] = wage_info["state"]
                        sal_copy["minimum_wage_effective_month"] = wage_info["effective_month"]
                        sal_copy["minimum_wage_effective_year"] = wage_info["effective_year"]
                    elif strict:
                        raise ValueError(
                            f"No statutory minimum wage revision found for employer work state '{sal_work_state}' on or before {m_int:02d}/{y_int}."
                        )
                else:
                    # Do not use candidate state as substitute
                    sal_copy["minimum_wage"] = None
                    sal_copy["minimum_wage_state"] = None
                    sal_copy["minimum_wage_effective_month"] = None
                    sal_copy["minimum_wage_effective_year"] = None
                    if strict:
                        if sal_emp_status == "UNSUPPORTED_STATE":
                            raise ValueError(f"Employer place of work is in an unsupported state. Minimum wage cannot be populated.")
                        elif sal_emp_status == "AMBIGUOUS":
                            raise ValueError(f"Employer place of work is ambiguous. Please specify district or state.")
                        else:
                            raise ValueError(f"Employer work state could not be identified for salary calculation.")
            except ValueError:
                if strict:
                    raise
            except Exception as exc:
                logger.warning("Could not auto-populate minimum wage for salary (%s/%s): %s", m, y, exc)
                if strict:
                    raise

        enriched_salaries.append(sal_copy)

    return enriched_employers, enriched_salaries


def apply_authoritative_minimum_wages(
    candidate: dict[str, Any],
    salary_entries: list[dict[str, Any]],
    strict: bool = False,
    employer_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Populate authoritative minimum wage data into each salary entry.

    If employer_entries is provided, uses associated employer work_state.
    Otherwise falls back to candidate beneficiary state for legacy caller compatibility.
    """
    if employer_entries is not None:
        _, enriched_salaries = apply_authoritative_employer_and_salary_wages(
            candidate, employer_entries, salary_entries, strict=strict
        )
        return enriched_salaries

    # Legacy fallback: use candidate beneficiary state
    cand_state = get_candidate_state(candidate)
    if not cand_state:
        if strict:
            raise ValueError(
                f"Candidate {candidate.get('candidate_id')} does not have an authoritative beneficiary state (state_name) for minimum wage validation."
            )
        return salary_entries

    enriched: list[dict[str, Any]] = []
    for entry in salary_entries:
        entry_copy = dict(entry)
        m = entry_copy.get("month")
        y = entry_copy.get("year")
        if m and y:
            try:
                m_int = int(m)
                y_int = int(y)
                wage_info = lookup_minimum_wage_for_period(cand_state, m_int, y_int)
                if wage_info:
                    entry_copy["minimum_wage"] = wage_info["minimum_wage"]
                    entry_copy["minimum_wage_state"] = wage_info["state"]
                    entry_copy["minimum_wage_effective_month"] = wage_info["effective_month"]
                    entry_copy["minimum_wage_effective_year"] = wage_info["effective_year"]
                elif strict:
                    raise ValueError(
                        f"No statutory minimum wage revision found for state '{cand_state}' on or before {m_int:02d}/{y_int}."
                    )
            except ValueError:
                if strict:
                    raise
            except Exception as exc:
                logger.warning("Could not auto-populate minimum wage for %s (%s/%s): %s", cand_state, m, y, exc)
                if strict:
                    raise
        enriched.append(entry_copy)

    return enriched


