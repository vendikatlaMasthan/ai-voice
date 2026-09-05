"""
VoiceShield AI — PII Minimization and Data Masking Utility (Phase 6 Hardening)
Provides standardized, explainable masking for phone numbers, caller identifiers,
account numbers, and personal details across logs, audit events, and public API representations.
"""

import re
from typing import Any, Dict, List, Optional, Union


def mask_phone_number(phone: Optional[str]) -> str:
    """
    Masks a telephone number or caller ID, retaining country prefix/first 2 digits and last 4 digits.
    Middle digits are replaced with asterisks while preserving readability.
    Examples:
        "+1 (555) 123-4567" -> "+1 (5**) ***-4567"
        "+919876543210"   -> "+91******3210"
        "9876543210"       -> "98****3210"
        "4102"             -> "***2"
        None / ""          -> ""
    """
    if not phone:
        return ""

    clean_str = str(phone).strip()
    if len(clean_str) <= 5:
        return "*" * max(1, len(clean_str) - 2) + clean_str[-2:] if len(clean_str) > 2 else "*" * max(0, len(clean_str) - 1) + clean_str[-1:]

    # Identify positions of all digits
    digit_indices = [i for i, ch in enumerate(clean_str) if ch.isdigit()]
    if len(digit_indices) <= 5:
        return "*" * max(1, len(clean_str) - 2) + clean_str[-2:]

    # Keep first 2 digits and last 4 digits
    keep_prefix = min(2, len(digit_indices) - 4)
    keep_suffix = 4
    mask_indices = set(digit_indices[keep_prefix:-keep_suffix])

    masked_chars = [
        "*" if i in mask_indices else ch
        for i, ch in enumerate(clean_str)
    ]
    return "".join(masked_chars)


def mask_email(email: Optional[str]) -> str:
    """
    Masks an email address:
        "john.doe@enterprise.com" -> "j******e@enterprise.com"
    """
    if not email or "@" not in email:
        return email or ""

    parts = email.split("@", 1)
    user, domain = parts[0], parts[1]
    if len(user) <= 2:
        masked_user = user[0] + "*"
    else:
        masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
    return f"{masked_user}@{domain}"


def mask_caller_context(context_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a copy of the context dictionary with sensitive PII masked for audit logs or external output.
    Does NOT mutate the original dictionary so internal fraud engines can access raw values.
    """
    if not isinstance(context_dict, dict):
        return {}

    sanitized = dict(context_dict)

    if "caller_id" in sanitized and sanitized["caller_id"]:
        sanitized["caller_id_masked"] = mask_phone_number(str(sanitized["caller_id"]))
        sanitized["caller_id"] = sanitized["caller_id_masked"]

    if "contact_phone" in sanitized and sanitized["contact_phone"]:
        sanitized["contact_phone"] = mask_phone_number(str(sanitized["contact_phone"]))

    if "email" in sanitized and sanitized["email"]:
        sanitized["email"] = mask_email(str(sanitized["email"]))

    return sanitized
