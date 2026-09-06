"""Tests de couverture pour app/query_weaviate.py."""

from unittest.mock import MagicMock, patch

import query_weaviate as qw


class TestQueryWeaviateConstants:
    """Vérifie les constantes du module."""

    def test_query_text_value(self):
        assert qw.QUERY_TEXT == "What is Unity Catalog?"

    def test_limit_value(self):
        assert qw.LIMIT == 3


class TestMain:
    """Tests pour la fonction `main` (script CLI)."""

    def test_main_with_no_results(self):
        """main() affiche 'Aucun résultat' si collection vide."""
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 768

        with patch.object(qw, "HuggingFaceEmbeddings", return_value=mock_embeddings):
            with patch.object(qw, "config") as mock_config:
                mock_config.EMBEDDING_MODEL_NAME = "test-model"
                mock_config.EMBEDDING_DEVICE = "cpu"
                mock_config.NORMALIZE_EMBEDDINGS = True
                mock_config.WEAVIATE_HOST = "localhost"
                mock_config.WEAVIATE_PORT = 9090
                mock_config.WEAVIATE_GRPC_PORT = 50051
                mock_config.ALPHA = 0.7
                mock_config.get_collection.return_value = "TestCollection"

                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_response = MagicMock()
                mock_response.objects = []  # Aucun résultat
                mock_collection.query.hybrid.return_value = mock_response
                mock_client.collections.get.return_value = mock_collection

                with patch.object(qw, "weaviate") as mock_weaviate:
                    mock_weaviate.connect_to_local.return_value = mock_client
                    with patch("sys.argv", ["query_weaviate.py"]):
                        with patch("builtins.print") as mock_print:
                            qw.main()
                            # Devrait afficher "Aucun résultat."
                            assert any("Aucun résultat" in str(call) for call in mock_print.call_args_list)

    def test_main_with_results(self):
        """main() affiche les résultats si trouvés."""
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 768

        with patch.object(qw, "HuggingFaceEmbeddings", return_value=mock_embeddings):
            with patch.object(qw, "config") as mock_config:
                mock_config.EMBEDDING_MODEL_NAME = "test-model"
                mock_config.EMBEDDING_DEVICE = "cpu"
                mock_config.NORMALIZE_EMBEDDINGS = True
                mock_config.WEAVIATE_HOST = "localhost"
                mock_config.WEAVIATE_PORT = 9090
                mock_config.WEAVIATE_GRPC_PORT = 50051
                mock_config.ALPHA = 0.7
                mock_config.get_collection.return_value = "TestCollection"

                mock_obj = MagicMock()
                mock_obj.properties = {
                    "content": "test content",
                    "source": "https://example.com",
                    "loc": "doc.md",
                    "chunk_index": 0,
                }
                mock_obj.metadata.distance = 0.1

                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_response = MagicMock()
                mock_response.objects = [mock_obj]
                mock_collection.query.hybrid.return_value = mock_response
                mock_client.collections.get.return_value = mock_collection

                with patch.object(qw, "weaviate") as mock_weaviate:
                    mock_weaviate.connect_to_local.return_value = mock_client
                    with patch("sys.argv", ["query_weaviate.py"]):
                        with patch("builtins.print") as mock_print:
                            qw.main()
                            # Devrait afficher "Résultat #1"
                            assert any("Résultat #1" in str(call) for call in mock_print.call_args_list)


def test_module_has_query_text():
    """QUERY_TEXT est défini."""
    assert hasattr(qw, "QUERY_TEXT")
    assert isinstance(qw.QUERY_TEXT, str)


def test_module_has_limit():
    """LIMIT est défini."""
    assert hasattr(qw, "LIMIT")
    assert qw.LIMIT == 3
