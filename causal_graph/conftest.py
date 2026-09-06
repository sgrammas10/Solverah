import os


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: hits the real OpenAI API, costs money, needs OPENAI_API_KEY "
        "(deselected by default -- run with -m live to include it)",
    )

    # 2026-09-06 incident: run_probe_gate_test.py, run_calibration_test.py, and
    # probe_boundary_test.py match pytest's *_test.py discovery glob but (before being
    # wrapped in main()/__main__ guards) made real OpenAI calls at MODULE level -- i.e.
    # during collection/import, not inside a test function. `-m "not live"` only
    # deselects test *functions*; it does nothing to stop module-level code from running
    # on import, and that gap produced 3 unintended live charges. The guards fix the
    # scripts we know about, but a future script in this directory could reintroduce the
    # same pattern. Rather than trust every file here to stay guarded, poison the API key
    # for the whole process unless this is a deliberate live run, so any stray
    # import-time call fails on auth instead of quietly billing.
    markexpr = config.getoption("markexpr") or ""
    deliberate_live = (
        ("live" in markexpr and "not live" not in markexpr)
        or os.environ.get("SOLVERAH_ALLOW_LIVE_CALLS") == "1"
    )
    if not deliberate_live:
        os.environ["OPENAI_API_KEY"] = "sk-invalid-blocked-by-conftest"
        print(
            "\n[causal_graph/conftest.py] non-live run -- OPENAI_API_KEY poisoned to block "
            "accidental module-level API calls (pass -m live or set "
            "SOLVERAH_ALLOW_LIVE_CALLS=1 for a deliberate live run)"
        )
