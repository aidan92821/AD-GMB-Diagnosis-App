import pytest
from unittest.mock import patch, MagicMock
from src.pipeline.qiime_preproc import qiime_preprocess
from src.pipeline.qiime2_runner import QiimeRunner


def test_taxonomy_classification_error_message():
    """Test that the taxonomy classification error provides helpful external tool suggestions."""

    # Mock the QiimeRunner to simulate the missing plugin error
    with patch('src.pipeline.qiime_preproc.QiimeRunner') as mock_runner_class:
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner

        # Mock the classify_taxa method to raise the specific error
        mock_runner.classify_taxa.side_effect = Exception("No such plugin: 'q2-feature-classifier'")

        # Mock other methods to avoid actual processing
        mock_runner.import_data.return_value = None
        mock_runner.denoise.return_value = None
        mock_runner.create_tables.return_value = None

        # Capture log messages
        log_messages = []
        def mock_log(msg):
            log_messages.append(msg)

        with patch('src.pipeline.qiime_preproc._log', side_effect=mock_log):
            # Call the function (it should handle the error gracefully)
            qiime_preprocess(
                bioproject="test_project",
                lib_layout="paired",
                callback=None
            )

        # Check that the appropriate error messages were logged
        assert any("Taxonomy classification not available: q2-feature-classifier plugin has been removed from QIIME 2 2024.10" in msg for msg in log_messages)
        assert any("** WARNING: Taxonomy assignment skipped. Genus-level analysis will not be available. **" in msg for msg in log_messages)
        assert any("** q2-feature-classifier is no longer available in QIIME 2. **" in msg for msg in log_messages)
        assert any("** For taxonomy classification, use external tools like: **" in msg for msg in log_messages)
        assert any("** - BLAST against SILVA database **" in msg for msg in log_messages)
        assert any("** - Kraken 2 with SILVA database **" in msg for msg in log_messages)
        assert any("** - SINTAX with SILVA classifier **" in msg for msg in log_messages)
        assert any("** - QIIME 2 2023.9 or earlier (if repositories available) **" in msg for msg in log_messages)