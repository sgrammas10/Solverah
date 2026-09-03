"""Extract text from one resume file, in a process of its very own.

Run as a script, never imported::

    python .../resume_extract/worker.py <mime> <input-path> <output-path>

**Why a separate process at all.**  ``pdfminer`` and ``python-docx`` are being
pointed at a file a stranger uploaded, and neither offers a way to bound how
long it will work or how much memory it will ask for.  In-process that is
unbounded: SECURITY_AUDIT_2026-09 5.1 is one crafted PDF holding a request
thread for as long as it likes -- gunicorn's own ``timeout`` catches a worker
whose process stops heartbeating, not one of eight threads that is simply busy
-- and 5.2 is a decompression bomb taking the whole interpreter's memory with
it.

The obvious in-process bound -- ``signal.alarm``/``SIGALRM`` -- cannot be used
here for two independent reasons, either of which is fatal on its own.  Signals
are delivered to the main thread, and production runs ``gthread`` workers where
a parse happens on one of eight non-main threads; and ``SIGALRM`` does not
exist on Windows, where the same code runs on every development machine.  A
child process can be killed from any thread on either platform, so that is the
mechanism.  The parent supplies the deadline
(``resume_service.PARSE_TIMEOUT_SECONDS``) and does the killing.

**What this file is responsible for**, given the parent already holds the
deadline: keeping a memory blowup from outliving its usefulness.  A parse that
allocates its way to the machine's limit can take the box down well inside a
generous timeout, so the address space is capped here, at the only point where
the limit applies to the parser and to nothing else.  ``resource`` is
POSIX-only; on Windows the cap is simply absent and the deadline is the whole
of the containment, which is the honest state of affairs rather than a silent
one -- see :func:`_cap_address_space`.

Text goes to a file rather than to stdout: the libraries below log to stderr
and are entitled to write to stdout, and a parser's warning arriving in the
middle of a resume is not a failure mode worth owning.  Exit status is the
channel -- 0 with the output file written, non-zero for anything else.
"""

from __future__ import annotations

import sys

#: Ceiling on the child's address space, in bytes.
#:
#: Generous against the 10 MB upload cap (``solverah/infra/storage.py``): a
#: pathological but real PDF can want a few hundred megabytes, and refusing
#: those would be a parser regression dressed up as a security control.  What it
#: stops is the order-of-magnitude case -- the 10 GB expansion in audit 5.2 --
#: where the failure is the machine rather than the file.
ADDRESS_SPACE_LIMIT_BYTES = 1024 * 1024 * 1024

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _cap_address_space() -> None:
    """Limit this process's address space where the platform can.

    Best-effort on purpose.  ``resource`` is absent on Windows, and a hardened
    container can refuse to lower an already-lowered limit; in both cases the
    parse should still run under the parent's deadline rather than fail closed
    over a control that was never available.
    """
    try:
        import resource
    except ImportError:
        return

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = ADDRESS_SPACE_LIMIT_BYTES
        if hard != resource.RLIM_INFINITY:
            ceiling = min(ceiling, hard)
        if soft == resource.RLIM_INFINITY or soft > ceiling:
            resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
    except (ValueError, OSError):
        return


def extract(mime: str, input_path: str) -> str:
    """Return the text of *input_path*, or "" for a MIME this cannot read."""
    if mime == PDF_MIME:
        from pdfminer.high_level import extract_text

        return extract_text(input_path) or ""

    if mime == DOCX_MIME:
        import docx

        document = docx.Document(input_path)
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()

    return ""


def main(argv: list) -> int:
    if len(argv) != 3:
        print("usage: worker.py <mime> <input-path> <output-path>", file=sys.stderr)
        return 2

    mime, input_path, output_path = argv
    _cap_address_space()

    text = extract(mime, input_path)
    with open(output_path, "w", encoding="utf-8", errors="replace") as handle:
        handle.write(text)
    return 0


if __name__ == "__main__":
    # No try/except: a parser that raises, a MemoryError from the cap above, or
    # a kill from the parent's deadline are all the same answer to the caller
    # ("this file did not yield text"), and the traceback belongs on stderr
    # where the parent logs it against the job id.
    sys.exit(main(sys.argv[1:]))
