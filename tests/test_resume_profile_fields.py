"""What a parsed resume turns into on the profile form (audit 2026-10-02).

Two bugs this pins:

* Item 2. The parser reports a role's dates as one ``duration`` string ("March
  2019 - Present"), and ``build_profile_from_resume_key`` put that whole string
  in ``endDate`` with ``startDate`` always "". The form's date inputs are
  ``type="month"``, which renders anything but ``YYYY-MM`` as blank, so every
  parsed role showed no dates at all -- and "Present" never ticked "I currently
  work here", because the box only checks for an ``endDate`` that IS "Present".
* Item 1, the half that lives here. A file with no readable text used to come
  back as an empty parse, which the job merged over the profile. It raises
  ``NoResumeText`` now; the anonymous intake, which has no profile to protect,
  still degrades to an empty parse.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from solverah.services import resume_service
from solverah.services.resume_service import NoResumeText, split_duration

TODAY = datetime.date(2026, 10, 2)


@pytest.mark.parametrize(
    "duration, expected",
    [
        ("March 2019 - Present", ("2019-03", "Present")),
        ("Jan 2018 – Dec 2020", ("2018-01", "2020-12")),
        ("Sept. 2017 — Current", ("2017-09", "Present")),
        ("06/2018 to 08/2020", ("2018-06", "2020-08")),
        ("3/15 - now", ("2015-03", "Present")),
        ("2016 - 2019", ("2016-01", "2019-12")),
        ("2021 - Present", ("2021-01", "Present")),
        ("March 2019", ("2019-03", "")),
        ("Summer internship", ("", "")),
        ("", ("", "")),
        (None, ("", "")),
    ],
)
def test_a_duration_splits_into_the_forms_month_fields(duration, expected):
    assert split_duration(duration, today=TODAY) == expected


def test_present_is_the_current_role_flag_never_a_date():
    start, end = split_duration("May 2022 - Present", today=TODAY)
    # The exact value ExperienceTab's checkbox writes and reads.
    assert end == "Present"
    assert start == "2022-05"


def test_an_impossible_month_is_left_blank_rather_than_invented():
    assert split_duration("13/2019 - 02/2020", today=TODAY) == ("", "2020-02")


def _parse_with(monkeypatch, text, parsed):
    monkeypatch.setattr(resume_service, "_download_and_extract", lambda key, mime: text)
    monkeypatch.setattr(resume_service, "parse_resume", lambda _text: parsed)
    return resume_service.build_profile_from_resume_key(
        resume_key="profile/1/abc/resume.pdf",
        resume_mime="application/pdf",
        resume_size_bytes=2048,
        resume_name="cv.pdf",
    )


def test_parsed_experience_carries_start_and_end_dates(monkeypatch):
    updates = _parse_with(
        monkeypatch,
        "some resume text",
        {"experience": [
            {"company": "Acme", "title": "Engineer", "duration": "March 2019 - Present"},
            {"company": "Initech", "title": "Intern", "duration": "Jun 2017 - Aug 2018"},
        ]},
    )

    first, second = updates["experience"]
    assert (first["startDate"], first["endDate"]) == ("2019-03", "Present")
    assert (second["startDate"], second["endDate"]) == ("2017-06", "2018-08")


@pytest.mark.parametrize("text", ["", "   \n\t "])
def test_a_file_with_no_text_raises_instead_of_returning_an_empty_parse(monkeypatch, text):
    monkeypatch.setattr(resume_service, "_download_and_extract", lambda key, mime: text)

    with pytest.raises(NoResumeText):
        resume_service.build_profile_from_resume_key(
            resume_key="profile/1/abc/resume.doc",
            resume_mime="application/msword",
            resume_size_bytes=2048,
        )


def test_a_storage_failure_is_not_reported_as_a_file_with_no_text(monkeypatch):
    """"Try a PDF or DOCX" would be the wrong advice for an R2 outage."""
    def _boom(key, mime):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(resume_service, "_download_and_extract", _boom)

    with pytest.raises(RuntimeError):
        resume_service.build_profile_from_resume_key(
            resume_key="profile/1/abc/resume.pdf",
            resume_mime="application/pdf",
            resume_size_bytes=2048,
        )


def test_the_intake_still_degrades_to_an_empty_parse_on_no_text(monkeypatch):
    """The anonymous intake starts from a blank profile, so there is nothing to
    wipe: it keeps the contact details and an empty parse, as documented."""
    monkeypatch.setattr(resume_service, "_download_and_extract", lambda key, mime: "")
    intake = SimpleNamespace(
        resume_key="intake/abc/resume.doc",
        resume_mime="application/msword",
        resume_size_bytes=2048,
        email="ada@example.com",
        first_name="Ada",
        last_name="Lovelace",
        phone=None,
        state="TX",
        linkedin_url=None,
    )

    profile = resume_service.build_profile_from_intake(intake)

    assert profile["firstName"] == "Ada"
    assert profile["experience"] == []
    assert profile["skills"] == []
    assert profile["uploadedResume"]["name"] == "resume.doc"
    assert profile["resumeKey"] == "intake/abc/resume.doc"
