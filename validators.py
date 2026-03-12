import re

# Only allow these profileData keys when saving
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
}

# Basic password rules for registration
def validate_password(p: str):
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


# Cleans incoming profile data to avoid malicious or junk fields
def clean_profile_data(profile_data: dict):
    cleaned = {}
    for k, v in profile_data.items():
        if k in ALLOWED_PROFILE_FIELDS:
            cleaned[k] = v
    return cleaned
