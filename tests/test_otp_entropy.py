"""Security tokens are drawn from `secrets`, not from `random`.

**The finding (2026-09 audit, HIGH).** `domain/auth.py` minted every 6-digit OTP
with `random.randint(100000, 999999)`. `random` is a Mersenne Twister: its
output is a pure function of 19937 bits of internal state, and that state is
recoverable from about 624 consecutive 32-bit outputs. One generator fed email
confirmation, resend, *and* password reset -- and `/auth/password/reset`
exchanges its code for a full session cookie without ever consulting
`password_hash`. So the attack needs no access to the victim's inbox: harvest a
stream of codes by self-registering and resending, reconstruct the state, call
`/auth/password/forgot` for the victim, predict the code, post it, receive the
victim's session.

**Why the shape of the test matters.** "Returns six digits" is what the old code
already did, so a test asserting only the format passes against the defect and
proves nothing. Predictability is a property of the *source*, and it is not
observable in any finite sample of the output -- which leaves two honest ways to
pin it, and this file uses both, because each covers the other's blind spot:

  * **Behavioural** (`test_the_code_comes_from_secrets_randbelow`,
    `test_random_is_never_consulted`): substitute the CSPRNG and watch the return
    value change; poison `random` and watch nothing touch it. This catches a
    regression anywhere in the call chain, including one that arrives through a
    helper this file has never heard of.

  * **Structural** (`test_no_module_under_solverah_imports_random`): parse the
    package and refuse the import outright. This catches a *new* module minting
    a token with `random` -- which the behavioural tests, being about
    `generate_verification_code` specifically, would never see.

The 2026-09 sweep found `random` in exactly one place under `solverah/`, this
one. The offline research scripts (`causal_graph/`, `company_culture_LLM/`,
`job_descr_LLM/`, `old_LLM/`) use it legitimately for retry jitter and synthetic
fixtures and are outside the guard's scope, because nothing there mints a
credential.
"""

import ast
import pathlib
import re
import secrets

import pytest

from solverah.domain import auth as domain

#: The application package. Deliberately not the repo root: the guard is about
#: code that serves requests, and the research trees are full of legitimate
#: `random.uniform` backoff jitter.
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "solverah"


# ── Format: unchanged, and it has to stay unchanged ─────────────────────────

def test_the_code_is_six_digits():
    """The wire format the SPA, the email template and the DB column all assume.

    `randbelow(900000) + 100000` spans 100000..999999 exactly, so `str` of it is
    always six characters with no zero-padding step to forget.
    """
    for _ in range(200):
        code = domain.generate_verification_code()
        assert re.fullmatch(r"[0-9]{6}", code), code


@pytest.mark.parametrize("draw,expected", [(0, "100000"), (899999, "999999")])
def test_both_ends_of_the_range_are_six_digits(monkeypatch, draw, expected):
    """An off-by-one in the shift would silently reshape the keyspace.

    `randbelow(1000000) + 100000` would run to 1099999 -- seven digits, which
    the column and the UI would truncate or reject. A bare `randbelow(900000)`
    would produce values below 100000, which `str` renders as five characters.
    Neither shows up reliably in a sample, so the two boundaries are driven
    directly instead of hoped for.
    """
    monkeypatch.setattr(secrets, "randbelow", lambda _n: draw)

    assert domain.generate_verification_code() == expected


# ── Source: the actual finding ──────────────────────────────────────────────

def test_the_code_comes_from_secrets_randbelow(monkeypatch):
    """Substituting the CSPRNG must change the answer.

    Fails against `random.randint`, which does not consult `secrets` at all: the
    sentinel below would be ignored and the assertion would compare against a
    real random code.
    """
    monkeypatch.setattr(secrets, "randbelow", lambda n: 424242 % n)

    assert domain.generate_verification_code() == str(424242 + 100000)


def test_randbelow_is_asked_for_the_right_span(monkeypatch):
    """900000, not 1000000 -- the span is what makes the format come out right."""
    spans = []
    monkeypatch.setattr(secrets, "randbelow", lambda n: spans.append(n) or 0)

    domain.generate_verification_code()

    assert spans == [900000]


def test_random_is_never_consulted(monkeypatch):
    """Poison every entry point on the Mersenne Twister and mint a code.

    This is the assertion that fails loudly against the pre-S1 code rather than
    merely comparing unequal: `random.randint` raises, so the test names the
    defect in its traceback.
    """
    import random

    def poisoned(*_a, **_k):
        raise AssertionError(
            "generate_verification_code reached the `random` module; OTPs must "
            "come from `secrets` (2026-09 audit finding 2.1)"
        )

    for name in ("randint", "randrange", "random", "choice", "getrandbits", "sample"):
        monkeypatch.setattr(random, name, poisoned)

    assert re.fullmatch(r"[0-9]{6}", domain.generate_verification_code())


# ── Structural guard: `random` cannot come back anywhere under solverah/ ────

def _python_files():
    return sorted(p for p in PACKAGE_ROOT.rglob("*.py"))


def test_the_guard_actually_sees_files():
    """A tree walk that matches nothing passes every assertion below it."""
    files = _python_files()

    assert len(files) > 20, files
    assert PACKAGE_ROOT / "domain" / "auth.py" in files


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_no_module_under_solverah_imports_random(path):
    """`import random` is banned in the request-serving package.

    Not "banned in `domain/auth.py`": the point of a guard is to catch the case
    nobody thought of, and the case nobody thought of is a *new* token minted in
    a new module. Nothing under `solverah/` needs a non-cryptographic PRNG
    today, so the blanket rule costs nothing and the exemption -- if some future
    module genuinely wants jitter -- is a deliberate edit to this list rather
    than a silent import.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue

        assert "random" not in names, (
            "%s:%d imports `random`. Security tokens must come from `secrets` "
            "(2026-09 audit finding 2.1). If this import is genuinely not "
            "minting a credential, exempt it here explicitly."
            % (path.relative_to(PACKAGE_ROOT.parent), node.lineno)
        )
