import re

# Only allow these profileData keys when saving
ALLOWED_PROFILE_FIELDS = {
    "firstName",
    "lastName",
    "email",
    "phone",
    "location",
    "summary",
    "experience",
    "education",
    "skills",
    "performanceReviews",
    "psychometricResults",
    "quizResults",
    "applications",
}

# Basic password rules for registration
def validate_password(p: str):
    if not p or len(p) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", p):
        return False, "Password must contain letters."
    if not re.search(r"[0-9]", p):
        return False, "Password must contain numbers."
    return True, None


# Cleans incoming profile data to avoid malicious or junk fields
def clean_profile_data(profile_data: dict):
    cleaned = {}
    for k, v in profile_data.items():
        if k in ALLOWED_PROFILE_FIELDS:
            cleaned[k] = v
    return cleaned