# tests/test_rewrite_app.py
"""Tests du branchement de la réécriture de requête dans chatbot/app.py."""

from unittest.mock import patch

from chatbot.app import rewrite_search_query


class TestRewriteSearchQuery:
    def test_returns_original_when_no_api_key(self):
        q = "unique no-key query"
        with patch("chatbot.app.OPENROUTER_API_KEY", None):
            with patch("chatbot.app.ChatOpenAI") as mock_llm:
                assert rewrite_search_query(q) == q
                mock_llm.assert_not_called()

    def test_returns_original_when_sentinel_api_key(self):
        q = "unique sentinel query"
        with patch("chatbot.app.OPENROUTER_API_KEY", "aaaaaaaaaaaaaaaaaaa"):
            with patch("chatbot.app.ChatOpenAI") as mock_llm:
                assert rewrite_search_query(q) == q
                mock_llm.assert_not_called()

    def test_returns_original_on_llm_error(self):
        q = "unique error query"
        with patch("chatbot.app.OPENROUTER_API_KEY", "k"):
            with patch("chatbot.app.ChatOpenAI") as mock_llm:
                mock_llm.return_value.invoke.side_effect = RuntimeError("boom")
                assert rewrite_search_query(q) == q

    def test_parses_rewritten_query(self):
        q = "unique happy path query"
        with patch("chatbot.app.OPENROUTER_API_KEY", "k"):
            with patch("chatbot.app.ChatOpenAI") as mock_llm:
                mock_llm.return_value.invoke.return_value.content = "Snowflake key concepts overview"
                assert rewrite_search_query(q) == "Snowflake key concepts overview"

    def test_empty_question_returns_as_is(self):
        assert rewrite_search_query("") == ""
