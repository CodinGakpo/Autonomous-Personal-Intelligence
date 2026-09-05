"""Tests for brain/profile.py — the per-user "About you" details and the identifiers the mail
pipeline derives from them."""

from brain import profile, store


def _conn(tmp_path):
    return store.connect(tmp_path / "t.db")


def test_profile_is_empty_by_default(tmp_path):
    assert profile.load_profile(_conn(tmp_path)) == []


def test_save_and_load_round_trip(tmp_path):
    conn = _conn(tmp_path)
    profile.save_profile(conn, [{"key": "Name", "value": "Adidev Anand"}])
    assert profile.load_profile(conn) == [{"key": "Name", "value": "Adidev Anand"}]


def test_save_replaces_rather_than_appends(tmp_path):
    conn = _conn(tmp_path)
    profile.save_profile(conn, [{"key": "Name", "value": "Old"}])
    profile.save_profile(conn, [{"key": "Name", "value": "New"}])
    assert profile.load_profile(conn) == [{"key": "Name", "value": "New"}]


def test_save_drops_entries_without_a_key(tmp_path):
    conn = _conn(tmp_path)
    saved = profile.save_profile(
        conn, [{"key": "  ", "value": "orphan"}, {"key": "Name", "value": "Adidev"}]
    )
    assert saved == [{"key": "Name", "value": "Adidev"}]


def test_identity_keys_become_attachment_identifiers():
    details = [
        {"key": "Name", "value": "Adidev Anand"},
        {"key": "Roll no", "value": "23BCE1234"},
        {"key": "Neo ID", "value": "N-9987"},
    ]
    assert profile.identifiers_from_profile(details) == [
        "Adidev Anand",
        "23BCE1234",
        "N-9987",
    ]


def test_identity_key_matching_ignores_case_and_punctuation():
    details = [{"key": "  ROLL   NUMBER ", "value": "23BCE1234"}]
    assert profile.identifiers_from_profile(details) == ["23BCE1234"]


def test_non_identity_details_are_not_identifiers():
    """Timezone or team must never be hunted for inside a spreadsheet."""
    details = [
        {"key": "Timezone", "value": "IST"},
        {"key": "Team", "value": "Placements"},
        {"key": "Company name", "value": "Hevo"},
    ]
    assert profile.identifiers_from_profile(details) == []


def test_an_identifiers_row_can_hold_several_comma_separated_values():
    details = [{"key": "Identifiers", "value": "Adidev Anand, 23BCE1234 , N-9987"}]
    assert profile.identifiers_from_profile(details) == [
        "Adidev Anand",
        "23BCE1234",
        "N-9987",
    ]


def test_very_short_values_are_rejected():
    """A one- or two-character "identifier" would match far too much text to be useful."""
    assert profile.identifiers_from_profile([{"key": "Name", "value": "AB"}]) == []


def test_duplicate_identifiers_are_collapsed():
    details = [
        {"key": "Name", "value": "Adidev Anand"},
        {"key": "Identifiers", "value": "Adidev Anand"},
    ]
    assert profile.identifiers_from_profile(details) == ["Adidev Anand"]
