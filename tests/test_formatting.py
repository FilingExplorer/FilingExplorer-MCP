from filingexplorer_mcp.formatting import page_note, slice_text, to_text


def test_drops_empty_values_and_inlines_scalar_lists():
    out = to_text({"a": 1, "b": None, "c": [], "d": ["x", "y"], "e": {"f": ""}})
    assert out == "a: 1\nd: [x, y]"


def test_lists_of_mappings():
    out = to_text({"rows": [{"k": "v", "n": 2}, {"k": "w"}]})
    assert out == "rows:\n  - k: v\n    n: 2\n  - k: w"


def test_quotes_ambiguous_strings():
    out = to_text({"a": "yes", "b": "x: y", "c": " pad", "d": True})
    assert out == 'a: "yes"\nb: "x: y"\nc: " pad"\nd: true'


def test_multiline_block():
    assert to_text({"t": "one\ntwo"}) == "t: |\n  one\n  two"


def test_empty_payload():
    assert to_text({}) == "(no data)"


def test_page_note():
    assert page_note(10, 0, 10, False) == ""
    assert "offset=5" in page_note(10, 0, 5, None)


def test_slice_text_last_window():
    assert slice_text("abcdef", 4, 10).startswith("[characters 4-6 of 6; end of text]")
    assert slice_text("abc", 0, 10) == "abc"


def test_nulls_inside_lists_keep_their_position():
    out = to_text({"values": [1, None, 3], "empty": [None, None]})
    assert out == "values: [1, null, 3]"
    assert to_text({"rows": [None, "a"]}) == "rows: [null, a]"
