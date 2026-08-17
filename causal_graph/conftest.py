def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: hits the real OpenAI API, costs money, needs OPENAI_API_KEY "
        "(deselected by default -- run with -m live to include it)",
    )
