"""Input validation and data sanitization utilities.

Used at the API boundary to:
  - Enforce password strength rules at registration / password-change time.
  - Strip unknown keys from profile payloads before they are written to the DB,
    preventing junk-field pollution and potential over-posting attacks.
"""

import re

# Whitelist of top-level keys permitted in a user's profile_data JSON blob.
# Any key NOT in this set is silently dropped by clean_profile_data().
ALLOWED_PROFILE_FIELDS = {
    "firstName",
    "lastName",
    "email",
    "phone",
    "location",
    "primaryLocation",
    "secondaryLocations",
    "summary",
    "experience",
    "education",
    "skills",
    "performanceReviews",
    "psychometricResults",
    "quizResults",
    "applications",
    "uploadedResume",
    "resumeKey",
    "linkedinUrl",
}

def validate_password(p: str) -> tuple[bool, str | None]:
    """Validate a plaintext password against Solverah's strength policy.

    Rules:
        - At least 12 characters long.
        - Contains at least one uppercase letter (A–Z).
        - Contains at least one lowercase letter (a–z).
        - Contains at least one digit (0–9).
        - Contains at least one non-alphanumeric symbol.

    Returns:
        (True, None) if the password passes all checks.
        (False, <human-readable error message>) on the first failing rule.
    """
    if not p or len(p) < 12:
        return False, "Password must be at least 12 characters."
    if not re.search(r"[A-Z]", p):
        return False, "Password must contain an uppercase letter."
    if not re.search(r"[a-z]", p):
        return False, "Password must contain a lowercase letter."
    if not re.search(r"[0-9]", p):
        return False, "Password must contain a number."
    if not re.search(r"[^A-Za-z0-9]", p):
        return False, "Password must contain a symbol."
    return True, None


def clean_profile_data(profile_data: dict) -> dict:
    """Return a copy of *profile_data* containing only whitelisted keys.

    Drops any key not in ALLOWED_PROFILE_FIELDS to guard against over-posting
    (a client sending unexpected fields that get persisted to the JSON column).

    Args:
        profile_data: Raw dict from the request body's ``profileData`` field.

    Returns:
        Sanitized dict with only allowed keys preserved.
    """
    cleaned = {}
    for k, v in profile_data.items():
        if k in ALLOWED_PROFILE_FIELDS:
            cleaned[k] = v
    return cleaned
