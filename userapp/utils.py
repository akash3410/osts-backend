import re
import random
from django.contrib.auth import get_user_model

User = get_user_model()


def generate_username_suggestions(raw_username, first_name="", last_name="", count=4):
    """
    Generate a list of available, valid username suggestions when a candidate
    username is already taken or invalid.
    """
    raw = (raw_username or "").strip().lower()
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", raw)
    if not base or len(base) < 2:
        base = "user"

    candidates = []

    # 1. First + Last name variations if provided
    fn = re.sub(r"[^a-zA-Z0-9]", "", (first_name or "").strip().lower())
    ln = re.sub(r"[^a-zA-Z0-9]", "", (last_name or "").strip().lower())
    if fn and ln:
        candidates.append(f"{fn}{ln}")
        candidates.append(f"{fn}_{ln}")
        candidates.append(f"{fn}.{ln}")
        candidates.append(f"{fn[0]}{ln}")
    elif fn:
        candidates.append(f"{fn}_{random.randint(10, 99)}")

    # 2. Base + number / suffix variations
    current_year_suffix = "26"
    candidates.extend([
        f"{base}{random.randint(10, 99)}",
        f"{base}_{random.randint(10, 99)}",
        f"{base}{current_year_suffix}",
        f"{base}_{random.randint(100, 999)}",
        f"{base}_official",
        f"{base}{random.randint(100, 999)}",
        f"{base}_dev",
    ])

    suggestions = []
    seen = {raw.lower()}

    for candidate in candidates:
        candidate_clean = candidate.strip()
        cand_lower = candidate_clean.lower()
        if cand_lower in seen:
            continue
        seen.add(cand_lower)

        if len(candidate_clean) < 3 or len(candidate_clean) > 150:
            continue

        if not User.objects.filter(username__iexact=candidate_clean).exists():
            suggestions.append(candidate_clean)
            if len(suggestions) >= count:
                break

    # If still not enough, generate random numeric fallbacks
    attempts = 0
    while len(suggestions) < count and attempts < 15:
        attempts += 1
        fallback = f"{base}_{random.randint(1000, 9999)}"
        if fallback.lower() not in seen:
            seen.add(fallback.lower())
            if not User.objects.filter(username__iexact=fallback).exists():
                suggestions.append(fallback)

    return suggestions
