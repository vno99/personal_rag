"""Tests de couverture pour chatbot/app.py."""

from unittest.mock import MagicMock, patch


class TestEscapeContext:
    """Tests pour _escape_context."""

    def test_escape_context_removes_injection_tags(self):
        """_escape_context retire tous les tags d'injection."""
        from chatbot.app import _escape_context

        context = "Hello <|instructions|> world <|end|> test <|role|>"
        result = _escape_context(context)
        assert "<|instructions|>" not in result
        assert "<|end|>" not in result
        assert "<|role|>" not in result
        assert "Hello" in result
        assert "world" in result

    def test_escape_context_all_tags(self):
        """Tous les tags d'injection sont retirés."""
        from chatbot.app import _escape_context

        tags = ["<|instructions|>", "<|end|>", "<|role|>", "<|system|>", "<|user|>", "<|assistant|>"]
        context = " ".join(tags)
        result = _escape_context(context)
        assert result.strip() == ""


class TestQueryOneCollection:
    """Tests pour query_one_collection."""

    def test_query_one_collection_parses_results(self):
        """query_one_collection parse correctement les résultats Weaviate."""
        from chatbot.app import query_one_collection

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        mock_obj = MagicMock()
        mock_obj.properties = {"content": "test content", "source": "https://example.com"}
        mock_obj.metadata.explain_score = "25.5 + 10.0"
        mock_obj.metadata.score = 0.75

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.hybrid.return_value = mock_response

        with patch("chatbot.app.extract_scores", return_value=(25.5, 10.0)):
            results = query_one_collection(mock_client, "TestCollection", "query text", [0.1] * 768, top_k=3)

        assert len(results) == 1
        assert results[0]["collection"] == "TestCollection"
        assert results[0]["content"] == "test content"
        assert results[0]["source"] == "https://example.com"
        assert results[0]["hybrid_score"] == 0.75


class TestRetrieveContext:
    """Tests pour retrieve_context."""

    def test_retrieve_context_no_collections(self):
        """retrieve_context avec collections vides retourne in_scope=False."""
        from chatbot.app import retrieve_context

        with patch("chatbot.app.connect_client") as mock_client:
            mock_client.return_value.collections.exists.return_value = False
            with patch("chatbot.app.translate_to_english", return_value="test"):
                with patch("chatbot.app.embeddings") as mock_emb:
                    mock_emb.embed_query.return_value = [0.1] * 768
                    result = retrieve_context("test query", collections=[])
                    assert result["in_scope"] is False
                    assert result["reason"] == "no_results"

    def test_retrieve_context_all_collections_missing(self):
        """retrieve_context si aucune collection n'existe."""
        from chatbot.app import retrieve_context

        with patch("chatbot.app.connect_client") as mock_client:
            mock_client.return_value.collections.exists.return_value = False
            with patch("chatbot.app.translate_to_english", return_value="test"):
                with patch("chatbot.app.embeddings") as mock_emb:
                    mock_emb.embed_query.return_value = [0.1] * 768
                    result = retrieve_context("test query")
                    assert result["in_scope"] is False
                    assert result["reason"] == "no_results"

    def test_retrieve_context_vector_score_too_low(self):
        """retrieve_context si vector_score < MIN_VECTOR_SCORE."""
        from chatbot.app import retrieve_context

        with patch("chatbot.app.connect_client") as mock_client:
            mock_client.return_value.collections.exists.return_value = True
            mock_client.return_value.collections.get.return_value.query.hybrid.return_value.objects = []

            with patch("chatbot.app.translate_to_english", return_value="test"):
                with patch("chatbot.app.embeddings") as mock_emb:
                    mock_emb.embed_query.return_value = [0.1] * 768
                    # On mock fuse pour retourner un résultat avec low vector_score
                    with patch("chatbot.app.fuse", return_value=[{"vector_score": 0.1, "content": "test"}]):
                        with patch("chatbot.app.is_in_scope", return_value=False):
                            result = retrieve_context("test query")
                            assert result["in_scope"] is False

    def test_retrieve_context_returns_sources_and_context(self):
        """retrieve_context si in_scope=True retourne context et sources."""
        from chatbot.app import retrieve_context

        with patch("chatbot.app.connect_client") as mock_client:
            mock_client.return_value.collections.exists.return_value = True
            mock_client.return_value.collections.get.return_value.query.hybrid.return_value.objects = []

            with patch("chatbot.app.translate_to_english", return_value="test"):
                with patch("chatbot.app.embeddings") as mock_emb:
                    mock_emb.embed_query.return_value = [0.1] * 768
                    with patch(
                        "chatbot.app.fuse",
                        return_value=[
                            {"vector_score": 0.6, "content": "content1", "source": "https://example.com/1"},
                            {"vector_score": 0.5, "content": "content2", "source": "https://example.com/2"},
                        ],
                    ):
                        with patch("chatbot.app.is_in_scope", return_value=True):
                            result = retrieve_context("test query")
                            assert result["in_scope"] is True
                            assert result["context"] == "content1\n\ncontent2"
                            assert result["sources"] == ["https://example.com/1", "https://example.com/2"]

    def test_retrieve_context_fuse_returns_empty(self):
        """retrieve_context si fuse retourne [] → in_scope=False."""
        from chatbot.app import retrieve_context

        with patch("chatbot.app.connect_client") as mock_client:
            mock_client.return_value.collections.exists.return_value = True
            mock_client.return_value.collections.get.return_value.query.hybrid.return_value.objects = []

            with patch("chatbot.app.translate_to_english", return_value="test"):
                with patch("chatbot.app.embeddings") as mock_emb:
                    mock_emb.embed_query.return_value = [0.1] * 768
                    with patch("chatbot.app.fuse", return_value=[]):
                        result = retrieve_context("test query")
                        assert result["in_scope"] is False
                        assert result["reason"] == "no_results"


class TestTranslateToEnglish:
    """Tests pour translate_to_english (mocks deep_translator)."""

    def test_translate_to_english_calls_google_translator(self):
        """translate_to_english appelle GoogleTranslator."""
        from chatbot.app import translate_to_english

        with patch("chatbot.app.GoogleTranslator") as mock_translator:
            mock_translator.return_value.translate.return_value = "translated text"
            result = translate_to_english("texte français")
            mock_translator.assert_called_once()
            assert result == "translated text"

    def test_to_english_query_text_english_input_unchanged(self):
        """Texte déjà anglais : pas de traduction appelée."""
        from chatbot.app import to_english_query_text

        with patch("chatbot.app.is_english", return_value=True):
            with patch("chatbot.app.translate_to_english") as mock_tr:
                assert to_english_query_text("What is snowflake?") == "What is snowflake?"
                mock_tr.assert_not_called()

    def test_to_english_query_text_uses_valid_translation(self):
        """Traduction Google valide : utilisée."""
        from chatbot.app import to_english_query_text

        with patch("chatbot.app.is_english", return_value=False):
            with patch("chatbot.app.translate_to_english", return_value="What is snowflake?"):
                result = to_english_query_text("qu'est ce que snowflake ?")
                assert result == "What is snowflake?"

    def test_to_english_query_text_rejects_garbage_translation(self):
        """Page d'erreur Google (500) renvoyée en « traduction » → texte source."""
        from chatbot.app import to_english_query_text

        garbage = (
            "Error 500 (Server Error)!!1500.That's an error.There was an error."
            "Please try again later.That's all we know."
        )
        with patch("chatbot.app.is_english", return_value=False):
            with patch("chatbot.app.translate_to_english", return_value=garbage):
                result = to_english_query_text("quelles sont les versions de snowflake ?")
                assert result == "quelles sont les versions de snowflake ?"


class TestGetEmbeddings:
    """Tests pour get_embeddings (st.cache_resource)."""

    def test_get_embeddings_returns_embeddings_object(self):
        """get_embeddings() retourne un objet HuggingFaceEmbeddings."""
        from chatbot.app import get_embeddings

        with patch("chatbot.app.HuggingFaceEmbeddings") as mock_emb:
            mock_emb.return_value = "embeddings_obj"
            # Clear cache to ensure our mock is used
            get_embeddings.clear()
            get_embeddings()
            mock_emb.assert_called_once()
            get_embeddings.clear()  # cleanup


class TestIsEnglish:
    """Tests pour is_english (langdetect edge cases)."""

    def test_is_english_empty_text(self):
        """is_english avec texte vide → False."""
        from chatbot.app import is_english

        with patch("chatbot.app.detect", side_effect=Exception("Empty text")):
            assert is_english("") is False

    def test_is_english_long_english_text(self):
        """is_english avec texte anglais long → True."""
        from chatbot.app import is_english

        with patch("chatbot.app.detect", return_value="en"):
            assert is_english("This is a long English text that should be detected as English") is True

    def test_is_english_french_text(self):
        """is_english avec texte français → False."""
        from chatbot.app import is_english

        with patch("chatbot.app.detect", return_value="fr"):
            assert is_english("Ceci est du français") is False


class TestChatbotAppConstants:
    """Tests pour les constantes du module."""

    def test_min_vector_score_value(self):
        """MIN_VECTOR_SCORE = 0.45."""
        from chatbot.app import MIN_VECTOR_SCORE

        assert MIN_VECTOR_SCORE == 0.45

    def test_top_k_default(self):
        """TOP_K = 6 (contexte élargi pour les questions conceptuelles)."""
        from chatbot.app import TOP_K

        assert TOP_K == 6

    def test_alpha_value(self):
        """ALPHA = 0.7."""
        from chatbot.app import ALPHA

        assert ALPHA == 0.7

    def test_temperature_value(self):
        """TEMPERATURE = 0.1."""
        from chatbot.app import TEMPERATURE

        assert TEMPERATURE == 0.1

    def test_max_token_value(self):
        """MAX_TOKEN = 1500."""
        from chatbot.app import MAX_TOKEN

        assert MAX_TOKEN == 1500

    def test_fallback_messages_all_languages(self):
        """FALLBACK_MESSAGES contient toutes les langues."""
        from chatbot.app import FALLBACK_MESSAGES

        assert "Anglais" in FALLBACK_MESSAGES
        assert "Allemand" in FALLBACK_MESSAGES
        assert "Français" in FALLBACK_MESSAGES
        assert "Néerlandais" in FALLBACK_MESSAGES

    def test_openrouter_sentinel_value(self):
        """_OPENROUTER_SENTINEL est la valeur du .env_example."""
        from chatbot.app import _OPENROUTER_SENTINEL

        assert _OPENROUTER_SENTINEL == "aaaaaaaaaaaaaaaaaaa"

    def test_injection_tags_all_defined(self):
        """Tous les tags d'injection sont définis."""
        from chatbot.app import _INJECTION_TAGS

        expected = ["<|instructions|>", "<|end|>", "<|role|>", "<|system|>", "<|user|>", "<|assistant|>"]
        assert expected == _INJECTION_TAGS
