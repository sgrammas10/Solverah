# TEMPORARY mutation probe -- simulates someone adding an employer-facing endpoint that
# reaches the person-side scores. Moved to _to_delete/ immediately after the check.
from model import PersonDimensionScore

def employer_view_candidate(user_id):
    return PersonDimensionScore.query.filter_by(user_id=user_id).all()
