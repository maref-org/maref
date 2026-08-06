"""
Comprehensive tests for finding_models.py
"""

import pytest
from dataclasses import asdict
from typing import Any

from src.research.finding_models import (
    StructuredFinding,
    findings_to_strings,
    extract_structured,
)


class TestStructuredFinding:
    """Test the StructuredFinding dataclass"""

    def test_construction_with_all_fields(self) -> None:
        """Test construction with all fields provided"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[0.85, 0.87, 0.89],
            unit="%",
            direction="higher_is_better",
            metadata={"batch": "test", "model": "gpt-4"},
        )

        assert finding.content == "Test finding"
        assert finding.metric_name == "accuracy"
        assert finding.values == [0.85, 0.87, 0.89]
        assert finding.unit == "%"
        assert finding.direction == "higher_is_better"
        assert finding.metadata == {"batch": "test", "model": "gpt-4"}

    def test_construction_with_defaults(self) -> None:
        """Test construction with default values"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[0.85],
        )

        assert finding.content == "Test finding"
        assert finding.metric_name == "accuracy"
        assert finding.values == [0.85]
        assert finding.unit == ""  # default
        assert finding.direction == "neutral"  # default
        assert finding.metadata == {}  # default

    def test_post_init_empty_values(self) -> None:
        """Test __post_init__ handles empty values list"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[],
        )

        assert finding.values == [0.0]  # Should be populated with [0.0]

    def test_post_init_none_values(self) -> None:
        """Test __post_init__ handles None values (should not happen but test edge case)"""
        # This is a defensive test - values should never be None due to type hints
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[],  # Empty list triggers __post_init__
        )
        finding.values = []  # Manually set to empty to test property methods
        assert finding.mean == 0.0
        assert finding.min == 0.0
        assert finding.max == 0.0
        assert finding.latest == 0.0

    def test_mean_property(self) -> None:
        """Test mean property calculation"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[1.0, 2.0, 3.0, 4.0],
        )

        assert finding.mean == 2.5  # (1+2+3+4)/4 = 2.5

    def test_mean_property_empty_values(self) -> None:
        """Test mean property with empty values (after __post_init__)"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[0.0],  # __post_init__ will set this
        )

        assert finding.mean == 0.0

    def test_min_property(self) -> None:
        """Test min property"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[2.5, 1.0, 3.0, 0.5],
        )

        assert finding.min == 0.5

    def test_max_property(self) -> None:
        """Test max property"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[2.5, 1.0, 3.0, 0.5],
        )

        assert finding.max == 3.0

    def test_latest_property(self) -> None:
        """Test latest property returns last value"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[1.0, 2.0, 3.0, 4.0],
        )

        assert finding.latest == 4.0

    def test_latest_property_single_value(self) -> None:
        """Test latest property with single value"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[2.5],
        )

        assert finding.latest == 2.5

    def test_to_finding_string_with_unit(self) -> None:
        """Test conversion to finding string with unit"""
        finding = StructuredFinding(
            content="Model accuracy",
            metric_name="accuracy",
            values=[0.851, 0.872, 0.889],
            unit="%",
        )

        result = finding.to_finding_string()
        assert result == "Model accuracy: 0.851, 0.872, 0.889 %"

    def test_to_finding_string_without_unit(self) -> None:
        """Test conversion to finding string without unit"""
        finding = StructuredFinding(
            content="Model accuracy",
            metric_name="accuracy",
            values=[0.851, 0.872, 0.889],
        )

        result = finding.to_finding_string()
        assert result == "Model accuracy: 0.851, 0.872, 0.889"

    def test_to_finding_string_truncation(self) -> None:
        """Test conversion to finding string with truncation for many values"""
        finding = StructuredFinding(
            content="Model accuracy",
            metric_name="accuracy",
            values=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        result = finding.to_finding_string()
        assert result == "Model accuracy: 0.100, 0.200, 0.300, 0.400, 0.500 ... (10 samples)"

    def test_to_finding_string_single_value(self) -> None:
        """Test conversion to finding string with single value"""
        finding = StructuredFinding(
            content="Model accuracy",
            metric_name="accuracy",
            values=[0.851],
        )

        result = finding.to_finding_string()
        assert result == "Model accuracy: 0.851"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[0.85, 0.87, 0.89],
            unit="%",
            direction="higher_is_better",
            metadata={"batch": "test"},
        )

        result = finding.to_dict()
        expected = {
            "content": "Test finding",
            "metric_name": "accuracy",
            "values": [0.85, 0.87, 0.89],
            "unit": "%",
            "direction": "higher_is_better",
            "metadata": {"batch": "test"},
        }

        assert result == expected

    def test_to_dict_defaults(self) -> None:
        """Test conversion to dictionary with default values"""
        finding = StructuredFinding(
            content="Test finding",
            metric_name="accuracy",
            values=[0.85],
        )

        result = finding.to_dict()
        expected = {
            "content": "Test finding",
            "metric_name": "accuracy",
            "values": [0.85],
            "unit": "",
            "direction": "neutral",
            "metadata": {},
        }

        assert result == expected

    def test_direction_values(self) -> None:
        """Test that direction can accept various string values"""
        # Test valid direction values mentioned in docstring
        for direction in ["higher_is_better", "lower_is_better", "neutral"]:
            finding = StructuredFinding(
                content="Test finding",
                metric_name="accuracy",
                values=[0.85],
                direction=direction,
            )
            assert finding.direction == direction

    def test_metric_name_examples(self) -> None:
        """Test metric name examples from docstring"""
        metric_names = ["f1_score", "entropy", "fnr", "fpr", "accuracy"]
        
        for metric_name in metric_names:
            finding = StructuredFinding(
                content=f"Test {metric_name}",
                metric_name=metric_name,
                values=[0.85],
            )
            assert finding.metric_name == metric_name


class TestFindingsToStrings:
    """Test the findings_to_strings function"""

    def test_mixed_list(self) -> None:
        """Test with mixed list of strings and StructuredFindings"""
        structured = StructuredFinding(
            content="Structured finding",
            metric_name="accuracy",
            values=[0.85, 0.87],
            unit="%",
        )
        
        findings = [
            "Plain string finding 1",
            structured,
            "Plain string finding 2",
        ]
        
        result = findings_to_strings(findings)
        
        assert len(result) == 3
        assert result[0] == "Plain string finding 1"
        assert result[1] == "Structured finding: 0.850, 0.870 %"
        assert result[2] == "Plain string finding 2"

    def test_all_strings(self) -> None:
        """Test with all strings"""
        findings = [
            "Finding 1",
            "Finding 2",
            "Finding 3",
        ]
        
        result = findings_to_strings(findings)
        
        assert result == findings

    def test_all_structured(self) -> None:
        """Test with all StructuredFindings"""
        findings = [
            StructuredFinding(
                content="Finding 1",
                metric_name="accuracy",
                values=[0.85],
            ),
            StructuredFinding(
                content="Finding 2",
                metric_name="f1_score",
                values=[0.92],
            ),
        ]
        
        result = findings_to_strings(findings)
        
        assert len(result) == 2
        assert result[0] == "Finding 1: 0.850"
        assert result[1] == "Finding 2: 0.920"

    def test_empty_list(self) -> None:
        """Test with empty list"""
        result = findings_to_strings([])
        assert result == []


class TestExtractStructured:
    """Test the extract_structured function"""

    def test_mixed_list(self) -> None:
        """Test with mixed list of strings and StructuredFindings"""
        structured1 = StructuredFinding(
            content="Structured finding 1",
            metric_name="accuracy",
            values=[0.85],
        )
        structured2 = StructuredFinding(
            content="Structured finding 2",
            metric_name="f1_score",
            values=[0.92],
        )
        
        findings = [
            "Plain string finding 1",
            structured1,
            "Plain string finding 2",
            structured2,
        ]
        
        result = extract_structured(findings)
        
        assert len(result) == 2
        assert result[0] == structured1
        assert result[1] == structured2

    def test_all_strings(self) -> None:
        """Test with all strings"""
        findings = [
            "Finding 1",
            "Finding 2",
        ]
        
        result = extract_structured(findings)
        
        assert result == []

    def test_all_structured(self) -> None:
        """Test with all StructuredFindings"""
        findings = [
            StructuredFinding(
                content="Finding 1",
                metric_name="accuracy",
                values=[0.85],
            ),
            StructuredFinding(
                content="Finding 2",
                metric_name="f1_score",
                values=[0.92],
            ),
        ]
        
        result = extract_structured(findings)
        
        assert result == findings

    def test_empty_list(self) -> None:
        """Test with empty list"""
        result = extract_structured([])
        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])