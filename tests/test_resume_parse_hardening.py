"""SECURITY_AUDIT_2026-09 5.1 and 5.2: the resume parser is bounded and fenced.

Both findings are the same shape -- unbounded work on a file a stranger chose --
and in Scenario A they land on a request thread of a ``gthread`` worker with no
Celery behind it, so "unbounded" means one upload holding one of this service's
twenty-four threads until gunicorn gives up on it.

Every test here fails against the code as it was before the fix.  Most fail
because a name they reach for does not exist yet, which proves little on its
own, so two are written to touch nothing new at all and fail on the behaviour:

* :func:`test_the_parser_never_runs_in_the_calling_process` -- the old
  ``extract_resume_text`` called ``pdfminer`` inline, so the stand-in planted
  in this process answered the call.
* :func:`test_a_bomb_docx_yields_an_empty_parse_rather_than_an_exception` --
  the old code handed the archive straight to ``docx.Document``, which inflated
  it and then raised, out of a function whose contract is to return "".

The rest exercise the mechanism: that the deadline is enforced off the main
thread (where ``signal.alarm`` would have been silently useless), that a parser
dying takes only its own process with it, and that the guard does not reject
the ordinary Word documents it exists to protect.
"""

import os
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest

from solverah.services import resume_service

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _stub_worker(tmp_path: Path, body: str) -> Path:
    """A stand-in for the extraction worker, so a test can choose how it behaves.

    The real worker's contract is the whole of what is stubbed here: argv is
    ``(mime, input, output)``, text goes to the output file, and the exit status
    is the only channel for anything else.
    """
    path = tmp_path / "stub_worker.py"
    path.write_text(body, encoding="utf-8")
    return path


def _legitimate_docx(tmp_path: Path) -> Path:
    """A real .docx, written by python-docx, holding a plausible resume line."""
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Jane Roe")
    document.add_paragraph("Senior Widget Engineer, Acme")
    path = tmp_path / "resume.docx"
    document.save(str(path))
    return path


def _zip_declaring(tmp_path: Path, name: str, uncompressed_bytes: int) -> Path:
    """A .docx-shaped archive whose single member expands to *uncompressed_bytes*.

    NUL bytes because they compress to almost nothing: the point of the exercise
    is a small upload that becomes a large expansion, which is the whole of the
    5.2 attack.
    """
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"\0" * uncompressed_bytes)
    return path


# ── 5.1 The parse is out of process, and killed on a deadline ────────────────


def test_the_parser_never_runs_in_the_calling_process(tmp_path, monkeypatch):
    """The bound is a killable child; a parser called inline could not have one.

    Plants a stand-in for ``pdfminer.high_level.extract_text`` *in this
    process*. If extraction still happens here, the stand-in answers and its
    sentinel comes back -- which is exactly what the pre-fix code did, and why
    no timeout could be enforced over it from a worker thread.
    """
    pytest.importorskip("pdfminer.high_level")
    import pdfminer.high_level

    called = []

    def _sentinel(*_args, **_kwargs):
        called.append(True)
        return "PARSED-IN-THE-CALLING-PROCESS"

    monkeypatch.setattr(pdfminer.high_level, "extract_text", _sentinel)

    document = tmp_path / "resume.pdf"
    document.write_bytes(b"%PDF-1.4\nnot a real pdf\n%%EOF\n")

    text = resume_service.extract_resume_text(document, PDF_MIME)

    assert called == [], "the parser ran in the calling process"
    assert text == ""


def test_a_parse_that_never_returns_is_killed_at_the_deadline(tmp_path, monkeypatch):
    """A hung parse ends at the deadline, and ends the same way a bad file does.

    Run from a **non-main thread** on purpose. That is where a parse lives in
    production -- ``gthread``, three workers of eight threads -- and it is where
    ``signal.alarm`` would have delivered nothing at all while looking like a
    working timeout in a single-threaded test.
    """
    worker = _stub_worker(
        tmp_path,
        "import time\ntime.sleep(600)\n",
    )
    monkeypatch.setattr(resume_service, "_WORKER_PATH", worker)
    monkeypatch.setattr(resume_service, "PARSE_TIMEOUT_SECONDS", 2)

    document = tmp_path / "resume.pdf"
    document.write_bytes(b"%PDF-1.4\n")

    outcome = {}

    def _parse():
        started = time.monotonic()
        outcome["text"] = resume_service.extract_resume_text(document, PDF_MIME)
        outcome["elapsed"] = time.monotonic() - started

    thread = threading.Thread(target=_parse)
    thread.start()
    thread.join(timeout=60)

    assert not thread.is_alive(), "the parse was still running well past its deadline"
    assert outcome["text"] == ""
    assert outcome["elapsed"] < 30, (
        "took %.1fs against a 2s deadline" % outcome["elapsed"]
    )


def test_a_parser_that_dies_takes_only_its_own_process(tmp_path, monkeypatch):
    """Containment, not just timing: a crash is a failed parse, not a failed worker.

    ``os._exit`` stands in for the segfault class of parser bug -- no exception
    to catch, no traceback, the process simply stops. Inline, that is the
    gunicorn worker and every other request on it.
    """
    worker = _stub_worker(tmp_path, "import os\nos._exit(3)\n")
    monkeypatch.setattr(resume_service, "_WORKER_PATH", worker)

    document = tmp_path / "resume.pdf"
    document.write_bytes(b"%PDF-1.4\n")

    ours = os.getpid()
    assert resume_service.extract_resume_text(document, PDF_MIME) == ""
    assert os.getpid() == ours, "the parse was not in a process of its own"


def test_the_deadline_is_a_module_constant(tmp_path):
    """No environment variable turns the deadline off.

    There is no deployment in which the right answer to a parse that will not
    terminate is different, so the limit is a constant rather than config: a
    knob here is a way to disable the control by accident, and a way to disable
    it deliberately from outside the repository.
    """
    source = Path(resume_service.__file__).read_text(encoding="utf-8")

    assert isinstance(resume_service.PARSE_TIMEOUT_SECONDS, int)
    assert resume_service.PARSE_TIMEOUT_SECONDS > 0
    assert "PARSE_TIMEOUT_SECONDS" not in os.environ
    assert "environ" not in source.split("PARSE_TIMEOUT_SECONDS = ")[1].split("\n")[0]


def test_the_worker_runs_by_path_and_needs_nothing_from_the_repository(tmp_path):
    """The child is launched by path, so it must import only third-party code.

    Launching by path puts the worker's own directory on ``sys.path[0]`` instead
    of the repository root. An import of ``solverah`` anything would therefore
    fail in the child and succeed in every test that imported the worker
    directly -- so the check is a real subprocess, run the way production runs
    it, with the repository deliberately absent from the path.
    """
    assert resume_service._WORKER_PATH.exists()

    env = dict(os.environ)
    # Popped, not emptied: an empty PYTHONPATH is not portably the same as an
    # absent one, and the point of the run is a child with no help finding
    # anything.
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, str(resume_service._WORKER_PATH)],
        capture_output=True,
        timeout=60,
        cwd=str(Path(sys.executable).parent),
        env=env,
    )

    # Exit 2 is the worker's own usage message: it started, so every import it
    # needs resolved without the repository on the path.
    assert completed.returncode == 2, completed.stderr.decode("utf-8", "replace")
    assert b"usage:" in completed.stderr


def _load_worker():
    """Import the worker by path, the way it is executed.

    It is deliberately not importable as ``solverah.infra.resume_extract.worker``
    from a test either -- doing that here would exercise a path production never
    takes.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_resume_extract_worker_under_test", resume_service._WORKER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_worker_caps_its_address_space_where_the_platform_has_one(monkeypatch):
    """The memory half of the containment, checked on a machine without rlimits.

    ``resource`` is POSIX-only, so on Windows this code path is never taken and
    would otherwise ship to Linux having only ever been read. A stand-in module
    lets the arithmetic be asserted anywhere: the cap is applied, and it is
    lowered to the hard limit rather than above it.
    """
    worker = _load_worker()

    calls = []

    class _Resource:
        RLIMIT_AS = 9
        RLIM_INFINITY = -1

        @staticmethod
        def getrlimit(_which):
            return (-1, -1)  # soft and hard both unlimited

        @staticmethod
        def setrlimit(which, limits):
            calls.append((which, limits))

    monkeypatch.setitem(sys.modules, "resource", _Resource)
    worker._cap_address_space()

    assert calls == [(9, (worker.ADDRESS_SPACE_LIMIT_BYTES, -1))]


def test_the_worker_never_raises_the_cap_it_was_given(monkeypatch):
    """A container that already caps memory keeps its own, lower, number.

    Raising a limit that a platform set on purpose would be this code deciding
    it knows better than the deployment, and on a real hard limit the call would
    simply fail -- taking every parse with it.
    """
    worker = _load_worker()

    calls = []
    lower_hard = 128 * 1024 * 1024

    class _Resource:
        RLIMIT_AS = 9
        RLIM_INFINITY = -1

        @staticmethod
        def getrlimit(_which):
            return (-1, lower_hard)

        @staticmethod
        def setrlimit(which, limits):
            calls.append((which, limits))

    monkeypatch.setitem(sys.modules, "resource", _Resource)
    worker._cap_address_space()

    assert calls == [(9, (lower_hard, lower_hard))]


def test_the_worker_survives_a_platform_that_refuses_the_cap(monkeypatch):
    """No cap is a reason to parse under the deadline alone, not a reason to fail.

    Windows has no ``resource`` at all, and a hardened sandbox can refuse the
    call. Either way the parse must still happen: the deadline is the control
    that is always present.
    """
    worker = _load_worker()

    class _Refusing:
        RLIMIT_AS = 9
        RLIM_INFINITY = -1

        @staticmethod
        def getrlimit(_which):
            raise OSError("not permitted")

        @staticmethod
        def setrlimit(_which, _limits):  # pragma: no cover -- never reached
            raise AssertionError("should not be called")

    monkeypatch.setitem(sys.modules, "resource", _Refusing)

    worker._cap_address_space()  # returns quietly rather than raising
    assert worker.extract("application/octet-stream", "nonexistent") == ""


# ── 5.2 A .docx is measured before it is unzipped ────────────────────────────


def test_a_bomb_docx_yields_an_empty_parse_rather_than_an_exception(tmp_path):
    """The behavioural half of 5.2, written against the pre-fix surface only.

    Nothing here names a constant or a function the fix introduced, so it fails
    on the old code for the right reason: sixty-five megabytes were inflated out
    of a sixty-five kilobyte upload and ``docx.Document`` then raised, out of a
    function documented to return "" for a file it cannot read.
    """
    bomb = _zip_declaring(tmp_path, "bomb.docx", 65 * 1024 * 1024)

    assert resume_service.extract_resume_text(bomb, DOCX_MIME) == ""


def test_a_docx_over_the_absolute_cap_is_refused_unread(tmp_path):
    """The 10 GB-from-10 MB case, scaled down to something a suite can hold.

    Sixty-five megabytes of expansion out of a ~65 KB upload: past the cap, and
    the whole exploit in miniature. Pre-fix this reached ``docx.Document``,
    which inflated it and then raised -- out of a function whose contract is to
    return "".
    """
    bomb = _zip_declaring(
        tmp_path,
        "bomb.docx",
        resume_service.MAX_DOCX_UNCOMPRESSED_BYTES + 1024 * 1024,
    )

    assert bomb.stat().st_size < 1024 * 1024, "the archive itself must stay small"

    refusal = resume_service.docx_expansion_refusal(bomb)
    assert refusal is not None and "exceeds" in refusal

    assert resume_service.extract_resume_text(bomb, DOCX_MIME) == ""


def test_a_docx_with_an_absurd_ratio_is_refused_inside_the_absolute_cap(tmp_path):
    """The variant the absolute cap alone would miss.

    Four megabytes of expansion is nothing; four megabytes out of four kilobytes
    is not a document. Without the ratio test a bomb could sit just under the
    absolute cap and be waved through on every upload.
    """
    bomb = _zip_declaring(tmp_path, "ratio.docx", 4 * 1024 * 1024)

    declared = sum(
        entry.file_size for entry in zipfile.ZipFile(bomb).infolist()
    )
    assert declared < resume_service.MAX_DOCX_UNCOMPRESSED_BYTES

    refusal = resume_service.docx_expansion_refusal(bomb)
    assert refusal is not None and "ratio" in refusal

    assert resume_service.extract_resume_text(bomb, DOCX_MIME) == ""


def test_a_docx_that_is_not_a_zip_is_refused_rather_than_raised(tmp_path):
    """An unreadable archive and a hostile one leave by the same door.

    The declared MIME is the client's word, so a .docx that is not a zip is an
    ordinary event on this path, and it has to arrive as the same empty parse
    every other unreadable file produces.
    """
    junk = tmp_path / "resume.docx"
    junk.write_bytes(b"this is not a zip file")

    assert resume_service.docx_expansion_refusal(junk) is not None
    assert resume_service.extract_resume_text(junk, DOCX_MIME) == ""


def test_a_real_resume_docx_is_not_refused(tmp_path):
    """The guard's other half: it must not reject the files it exists to protect.

    A ratio cap set carelessly is a parser outage for everyone who writes their
    resume in Word, which is a worse outcome than the bomb it was meant to stop.
    """
    resume = _legitimate_docx(tmp_path)

    assert resume_service.docx_expansion_refusal(resume) is None
    assert "Jane Roe" in resume_service.extract_resume_text(resume, DOCX_MIME)
