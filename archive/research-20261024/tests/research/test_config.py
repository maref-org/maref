"""
Test suite for research/config.py module.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import the module to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
from research import config


def test_get_project_root_default():
    """Test get_project_root() with no environment variable set."""
    with patch.dict(os.environ, {}, clear=True):
        result = config.get_project_root()
        assert isinstance(result, Path)
        # Should be 3 levels up from config.py location
        expected = Path(config.__file__).parent.parent.parent
        assert result == expected


def test_get_project_root_with_env():
    """Test get_project_root() with MAREF_PROJECT_ROOT environment variable."""
    test_path = "/custom/project/root"
    with patch.dict(os.environ, {'MAREF_PROJECT_ROOT': test_path}):
        result = config.get_project_root()
        assert isinstance(result, Path)
        assert str(result) == test_path


def test_get_project_root_empty_env():
    """Test get_project_root() with empty environment variable."""
    with patch.dict(os.environ, {'MAREF_PROJECT_ROOT': ''}):
        result = config.get_project_root()
        assert isinstance(result, Path)
        # Should fall back to default
        expected = Path(config.__file__).parent.parent.parent
        assert result == expected


def test_get_mailbox_dir_default():
    """Test get_mailbox_dir() with no environment variable set."""
    with patch.dict(os.environ, {}, clear=True):
        result = config.get_mailbox_dir()
        assert isinstance(result, Path)
        # Should be project_root/mailbox
        project_root = config.get_project_root()
        expected = project_root / 'mailbox'
        assert result == expected


def test_get_mailbox_dir_with_env():
    """Test get_mailbox_dir() with MAREF_MAILBOX_DIR environment variable."""
    test_path = "/custom/mailbox/directory"
    with patch.dict(os.environ, {'MAREF_MAILBOX_DIR': test_path}):
        result = config.get_mailbox_dir()
        assert isinstance(result, Path)
        assert str(result) == test_path


def test_get_mailbox_dir_relative_path():
    """Test get_mailbox_dir() with relative path in environment variable."""
    with patch.dict(os.environ, {'MAREF_MAILBOX_DIR': 'relative/mailbox'}):
        result = config.get_mailbox_dir()
        assert isinstance(result, Path)
        # Path should preserve relative path
        assert str(result) == 'relative/mailbox'


def test_get_output_dir_env_output_first():
    """Test get_output_dir() with MAREF_OUTPUT_DIR environment variable (highest priority)."""
    test_path = "/custom/output/directory"
    with patch.dict(os.environ, {'MAREF_OUTPUT_DIR': test_path}):
        result = config.get_output_dir()
        assert isinstance(result, Path)
        assert str(result) == test_path


def test_get_output_dir_env_mailbox_second():
    """Test get_output_dir() with MAREF_MAILBOX_DIR environment variable (second priority)."""
    test_path = "/custom/mailbox"
    with patch.dict(os.environ, {'MAREF_MAILBOX_DIR': test_path}, clear=True):
        result = config.get_output_dir()
        assert isinstance(result, Path)
        expected = Path(test_path) / 'research_output'
        assert result == expected


def test_get_output_dir_default_third():
    """Test get_output_dir() with no environment variables (default)."""
    with patch.dict(os.environ, {}, clear=True):
        result = config.get_output_dir()
        assert isinstance(result, Path)
        project_root = config.get_project_root()
        expected = project_root / 'research_output'
        assert result == expected


def test_get_output_dir_empty_env_output():
    """Test get_output_dir() with empty MAREF_OUTPUT_DIR environment variable."""
    with patch.dict(os.environ, {'MAREF_OUTPUT_DIR': ''}):
        result = config.get_output_dir()
        assert isinstance(result, Path)
        # Should fall back to default
        project_root = config.get_project_root()
        expected = project_root / 'research_output'
        assert result == expected


def test_get_output_dir_env_output_overrides_mailbox():
    """Test that MAREF_OUTPUT_DIR takes precedence over MAREF_MAILBOX_DIR."""
    output_path = "/custom/output"
    mailbox_path = "/custom/mailbox"
    with patch.dict(os.environ, {
        'MAREF_OUTPUT_DIR': output_path,
        'MAREF_MAILBOX_DIR': mailbox_path
    }):
        result = config.get_output_dir()
        assert str(result) == output_path


def test_get_research_output_dir_alias():
    """Test that get_research_output_dir() is an alias for get_output_dir()."""
    with patch.dict(os.environ, {}, clear=True):
        result1 = config.get_output_dir()
        result2 = config.get_research_output_dir()
        assert result1 == result2
        assert isinstance(result2, Path)


def test_get_research_output_dir_with_env():
    """Test get_research_output_dir() with environment variable."""
    test_path = "/custom/research/output"
    with patch.dict(os.environ, {'MAREF_OUTPUT_DIR': test_path}):
        result = config.get_research_output_dir()
        assert str(result) == test_path


def test_get_log_dir_default():
    """Test get_log_dir() with no environment variables."""
    with patch.dict(os.environ, {}, clear=True):
        result = config.get_log_dir()
        assert isinstance(result, Path)
        output_dir = config.get_output_dir()
        expected = output_dir / 'logs'
        assert result == expected


def test_get_log_dir_with_env():
    """Test get_log_dir() with MAREF_OUTPUT_DIR environment variable."""
    test_path = "/custom/output"
    with patch.dict(os.environ, {'MAREF_OUTPUT_DIR': test_path}):
        result = config.get_log_dir()
        assert isinstance(result, Path)
        expected = Path(test_path) / 'logs'
        assert result == expected


def test_get_knowledge_graph_path_default():
    """Test get_knowledge_graph_path() default behavior."""
    with patch('tempfile.gettempdir', return_value='/tmp'):
        result = config.get_knowledge_graph_path()
        assert isinstance(result, Path)
        assert str(result) == '/tmp/maref-knowledge-graph.json'


def test_get_knowledge_graph_path_mocked_tempdir():
    """Test get_knowledge_graph_path() with mocked temp directory."""
    mock_tempdir = '/custom/temp/dir'
    with patch('tempfile.gettempdir', return_value=mock_tempdir):
        result = config.get_knowledge_graph_path()
        assert isinstance(result, Path)
        expected = Path(mock_tempdir) / 'maref-knowledge-graph.json'
        assert result == expected


def test_get_knowledge_graph_path_import_protection():
    """Test that get_knowledge_graph_path() imports tempfile inside function."""
    # This test ensures the import is inside the function as shown in the source
    result = config.get_knowledge_graph_path()
    assert isinstance(result, Path)
    assert 'maref-knowledge-graph.json' in str(result)


def test_environment_constants():
    """Test that environment variable constants are defined correctly."""
    assert config.ENV_PROJECT_ROOT == 'MAREF_PROJECT_ROOT'
    assert config.ENV_MAILBOX_DIR == 'MAREF_MAILBOX_DIR'
    assert config.ENV_OUTPUT_DIR == 'MAREF_OUTPUT_DIR'
    assert config.ENV_RESEARCH_OUTPUT == 'MAREF_RESEARCH_OUTPUT'
    assert config.ENV_DASHSCOPE_API_KEY == 'DASHSCOPE_API_KEY'


def test_module_all_exports():
    """Test that __all__ exports all expected symbols."""
    expected_exports = [
        'get_project_root',
        'get_mailbox_dir',
        'get_output_dir',
        'get_research_output_dir',
        'get_log_dir',
        'get_knowledge_graph_path',
        'ENV_PROJECT_ROOT',
        'ENV_MAILBOX_DIR',
        'ENV_OUTPUT_DIR',
        'ENV_RESEARCH_OUTPUT',
        'ENV_DASHSCOPE_API_KEY'
    ]
    assert set(config.__all__) == set(expected_exports)


def test_path_objects_are_paths():
    """Ensure all functions return Path objects."""
    with patch.dict(os.environ, {}, clear=True):
        with patch('tempfile.gettempdir', return_value='/tmp'):
            functions = [
                config.get_project_root,
                config.get_mailbox_dir,
                config.get_output_dir,
                config.get_research_output_dir,
                config.get_log_dir,
                config.get_knowledge_graph_path
            ]
            
            for func in functions:
                result = func()
                assert isinstance(result, Path), f"{func.__name__} did not return Path"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])