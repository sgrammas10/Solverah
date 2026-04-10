from validators import clean_profile_data, validate_password


def test_validate_password_rules():
    ok, msg = validate_password("Strongpass1!")
    assert ok is True
    assert msg is None

    ok, msg = validate_password("Short1!")
    assert ok is False
    assert msg == "Password must be at least 12 characters."

    ok, msg = validate_password("lowercase12!")
    assert ok is False
    assert msg == "Password must contain an uppercase letter."

    ok, msg = validate_password("UPPERCASE12!")
    assert ok is False
    assert msg == "Password must contain a lowercase letter."

    ok, msg = validate_password("NoNumbersXY!")
    assert ok is False
    assert msg == "Password must contain a number."

    ok, msg = validate_password("NoSymbol1234A")
    assert ok is False
    assert msg == "Password must contain a symbol."


def test_clean_profile_data_strips_unknown_keys():
    incoming = {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "email": "ada@example.com",
        "unknownField": "should_drop",
    }
    cleaned = clean_profile_data(incoming)
    assert "unknownField" not in cleaned
    assert cleaned["firstName"] == "Ada"
