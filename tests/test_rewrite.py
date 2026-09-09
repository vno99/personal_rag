# tests/test_rewrite.py
"""Tests unitaires de la réécriture de requête (chatbot/rewrite.py)."""

from rewrite import (
    build_rewrite_messages,
    is_plausible_translation,
    parse_search_query,
)


def test_build_rewrite_messages_system_and_user_roles():
    msgs = build_rewrite_messages("What is Snowflake")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"]


def test_build_rewrite_messages_embeds_question():
    msgs = build_rewrite_messages("What is Snowflake")
    assert "What is Snowflake" in msgs[1]["content"]


def test_build_rewrite_messages_asks_to_keep_code_verbatim():
    msgs = build_rewrite_messages("CREATE TABLE syntax")
    assert "verbatim" in msgs[1]["content"]


def test_parse_search_query_plain():
    assert parse_search_query("Snowflake key concepts overview", "fallback") == "Snowflake key concepts overview"


def test_parse_search_query_takes_last_non_empty_line():
    raw = "Here is a rewritten query:\nSnowflake overview key concepts"
    assert parse_search_query(raw, "fallback") == "Snowflake overview key concepts"


def test_parse_search_query_strips_backticks():
    assert parse_search_query("`Snowflake architecture overview`", "fallback") == "Snowflake architecture overview"


def test_parse_search_query_strips_quotes():
    assert parse_search_query('"Snowflake architecture overview"', "fallback") == "Snowflake architecture overview"


def test_parse_search_query_none_or_empty_returns_fallback():
    assert parse_search_query(None, "orig") == "orig"
    assert parse_search_query("", "orig") == "orig"


def test_parse_search_query_only_whitespace_returns_fallback():
    assert parse_search_query("   \n  \n", "orig") == "orig"


def test_build_rewrite_messages_demands_english_translation():
    msgs = build_rewrite_messages("quelles sont les versions ?")
    content = msgs[1]["content"]
    assert "not in English" in content
    assert "must be English" in content


def test_is_plausible_translation_normal():
    assert (
        is_plausible_translation(
            "What are the versions of snowflake?",
            "quelles sont les versions de snowflake ?",
        )
        is True
    )


def test_is_plausible_translation_google_500_error_page():
    garbage = (
        "Error 500 (Server Error)!!1500.That's an error.There was an error.Please try again later.That's all we know."
    )
    assert is_plausible_translation(garbage, "quelles sont les versions de snowflake ?") is False


def test_is_plausible_translation_none_or_whitespace():
    assert is_plausible_translation(None, "question") is False
    assert is_plausible_translation("   ", "question") is False


def test_is_plausible_translation_much_too_long():
    assert is_plausible_translation("a" * 500, "courte question") is False
