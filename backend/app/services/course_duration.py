"""CPASS Course Duration & Minimum CTC Validation Service.

Infers standard DDU-GKY course duration (3, 6, 9, 12 months) from Batch Start Date
and Batch End Date, determines the governing minimum CTC using the Higher-of-Two rule
between course minimum and statutory state minimum wage, and validates employer monthly CTC.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("cpass.course_duration")

# Standard course duration mapping: months -> minimum monthly CTC (in INR)
STANDARD_COURSE_DURATIONS: dict[int, float] = {
    3: 6000.0,
    6: 8000.0,
    9: 12000.0,
    12: 15000.0,
}

# The 28 Indian States (alphabetical order)
INDIAN_STATES_28: tuple[str, ...] = (
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
)

# The 8 Indian Union Territories (alphabetical order)
INDIAN_UTS_8: tuple[str, ...] = (
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
)

ALL_36_INDIAN_STATES_AND_UTS: tuple[str, ...] = INDIAN_STATES_28 + INDIAN_UTS_8


def parse_date_safe(val: Any) -> date | None:
    """Parse date from string, date, datetime or None safely.
    
    Supports ISO formats (YYYY-MM-DD), DD/MM/YYYY, DD-MM-YYYY, and handles
    strings like 'Not Available', 'N/A', empty strings, or nulls.
    """
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()

    s = str(val).strip()
    if not s or s.lower() in ("not available", "n/a", "none", "null", "undefined", "—", "-"):
        return None

    # Handle ISO datetime strings like "2024-01-15T00:00:00" or "2024-01-15 00:00:00"
    if "t" in s.lower():
        s = s.split("T")[0].split("t")[0]
    elif " " in s:
        s = s.split(" ")[0]

    # Try standard formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    return None


def calculate_course_duration(batch_start_date: Any, batch_end_date: Any) -> dict[str, Any]:
    """Infer course duration using batch start date and batch end date.
    
    Returns a dict with:
      - months: int (3, 6, 9, 12) or None
      - label: str (e.g. '3 Months') or None
      - minimum_ctc: float (e.g. 6000.0) or None
      - total_days: int or None
      - status: 'DETERMINED' | 'MISSING_DATES' | 'INVALID_DATES' | 'UNMATCHED_DURATION'
      - message: str or None (informational warning if not determined)
    """
    start = parse_date_safe(batch_start_date)
    end = parse_date_safe(batch_end_date)

    if not start or not end:
        return {
            "months": None,
            "label": None,
            "minimum_ctc": None,
            "total_days": None,
            "status": "MISSING_DATES",
            "message": "Course duration could not be reliably determined from the available batch dates. Course-based minimum CTC validation has been skipped. Available state minimum-wage validation will still be applied.",
        }

    if end < start:
        return {
            "months": None,
            "label": None,
            "minimum_ctc": None,
            "total_days": None,
            "status": "INVALID_DATES",
            "message": "Batch end date precedes batch start date. Course duration could not be reliably determined. Course-based minimum CTC validation has been skipped.",
        }

    # Inclusive calendar days
    total_days = (end - start).days + 1

    # Approximate month boundaries (based on ~30.4375 days/month):
    # 3 Months (~91 days): 65 to 137 days
    # 6 Months (~183 days): 138 to 228 days
    # 9 Months (~274 days): 229 to 319 days
    # 12 Months (~365 days): 320 to 425 days
    if total_days < 65:
        return {
            "months": None,
            "label": None,
            "minimum_ctc": None,
            "total_days": total_days,
            "status": "UNMATCHED_DURATION",
            "message": f"Batch duration ({total_days} days) is less than the standard 3-month course threshold. Course-based minimum CTC validation has been skipped.",
        }

    if total_days <= 137:
        matched_months = 3
    elif total_days <= 228:
        matched_months = 6
    elif total_days <= 319:
        matched_months = 9
    elif total_days <= 425:
        matched_months = 12
    else:
        return {
            "months": None,
            "label": None,
            "minimum_ctc": None,
            "total_days": total_days,
            "status": "UNMATCHED_DURATION",
            "message": f"Batch duration ({total_days} days) exceeds the standard 12-month course threshold. Course-based minimum CTC validation has been skipped.",
        }

    min_ctc = STANDARD_COURSE_DURATIONS[matched_months]
    return {
        "months": matched_months,
        "label": f"{matched_months} Months",
        "minimum_ctc": min_ctc,
        "total_days": total_days,
        "status": "DETERMINED",
        "message": None,
    }


def calculate_applicable_minimum_ctc(
    course_min_ctc: float | None,
    state_min_wage: float | None,
) -> dict[str, Any]:
    """Calculate the applicable minimum CTC using the Higher-of-Two rule:
    Applicable Minimum CTC = MAX(Course Minimum CTC, State Minimum Wage)
    
    Handles scenarios where one or both amounts are unavailable.
    """
    has_course = course_min_ctc is not None and course_min_ctc > 0
    has_state = state_min_wage is not None and state_min_wage > 0

    if has_course and has_state:
        applicable_min = max(float(course_min_ctc), float(state_min_wage))
        if float(course_min_ctc) > float(state_min_wage):
            governing_rule = "COURSE_DURATION_HIGHER"
        elif float(state_min_wage) > float(course_min_ctc):
            governing_rule = "STATE_WAGE_HIGHER"
        else:
            governing_rule = "EQUAL_AMOUNTS"
    elif has_course:
        applicable_min = float(course_min_ctc)
        governing_rule = "COURSE_DURATION_ONLY"
    elif has_state:
        applicable_min = float(state_min_wage)
        governing_rule = "STATE_WAGE_ONLY"
    else:
        applicable_min = None
        governing_rule = "NONE_AVAILABLE"

    return {
        "applicable_minimum_ctc": applicable_min,
        "course_minimum_ctc": float(course_min_ctc) if has_course else None,
        "state_minimum_wage": float(state_min_wage) if has_state else None,
        "governing_rule": governing_rule,
    }


def validate_employer_monthly_ctc(
    monthly_ctc: Any,
    course_duration_info: dict[str, Any],
    state_min_wage: float | None,
    employer_name: str = "",
) -> dict[str, Any]:
    """Validate employer monthly CTC against the governing applicable minimum.
    
    If monthly_ctc is below the applicable minimum, returns is_valid=False with
    a user-friendly formatted message suitable for display in UI popups or API errors.
    """
    course_min = course_duration_info.get("minimum_ctc")
    calc = calculate_applicable_minimum_ctc(course_min, state_min_wage)
    applicable_min = calc["applicable_minimum_ctc"]

    # Parse entered CTC
    entered_num = None
    if monthly_ctc is not None and str(monthly_ctc).strip():
        try:
            entered_num = float(monthly_ctc)
        except (ValueError, TypeError):
            entered_num = None

    # If neither course nor state wage can be determined, do not block submission
    if applicable_min is None:
        return {
            "is_valid": True,
            "entered_ctc": entered_num,
            "applicable_minimum_ctc": None,
            "course_duration_info": course_duration_info,
            "state_minimum_wage": state_min_wage,
            "user_message": None,
        }

    # If entered CTC is missing or below applicable minimum, validation fails
    if entered_num is None or entered_num < applicable_min:
        course_label = course_duration_info.get("label") or "Not Available"
        course_min_str = f"₹{int(course_min):,}" if course_min else "Not Available"
        state_wage_str = f"₹{int(state_min_wage):,}" if state_min_wage else "Unavailable"
        app_min_str = f"₹{int(applicable_min):,}"
        entered_str = f"₹{int(entered_num):,}" if entered_num is not None else "₹0 (Not Provided)"
        emp_prefix = f" for employer '{employer_name}'" if employer_name else ""

        message = (
            f"The entered monthly CTC{emp_prefix} is below the applicable minimum requirement for this placement.\n\n"
            f"Course Duration: {course_label}\n"
            f"Course Minimum CTC: {course_min_str}\n"
            f"State Minimum Wage: {state_wage_str}\n"
            f"Applicable Minimum CTC: {app_min_str}\n"
            f"Entered Monthly CTC: {entered_str}\n\n"
            f"Please update the Monthly CTC before submitting the Candidate Dossier."
        )

        return {
            "is_valid": False,
            "entered_ctc": entered_num,
            "applicable_minimum_ctc": applicable_min,
            "course_duration_info": course_duration_info,
            "state_minimum_wage": state_min_wage,
            "user_message": message,
            "title": "Minimum CTC Requirement Not Met",
        }

    return {
        "is_valid": True,
        "entered_ctc": entered_num,
        "applicable_minimum_ctc": applicable_min,
        "course_duration_info": course_duration_info,
        "state_minimum_wage": state_min_wage,
        "user_message": None,
    }
