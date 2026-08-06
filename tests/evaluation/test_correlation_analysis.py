"""Tests for human-AI correlation analysis."""

from maref.evaluation.correlation_analysis import (
    compute_spearman_rank, compute_correlation_report, RoundScore, CorrelationReport,
)


class TestSpearmanRank:
    def test_perfect_positive(self):
        x = [1, 2, 3, 4, 5]
        y = [1, 2, 3, 4, 5]
        rho, p = compute_spearman_rank(x, y)
        assert abs(rho - 1.0) < 0.01

    def test_perfect_negative(self):
        x = [1, 2, 3]
        y = [3, 2, 1]
        rho, p = compute_spearman_rank(x, y)
        assert abs(rho - (-1.0)) < 0.01

    def test_no_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [5, 1, 4, 2, 3]
        rho, p = compute_spearman_rank(x, y)
        assert abs(rho) < 0.5

    def test_too_few_samples(self):
        x = [1, 2]
        y = [1, 2]
        rho, p = compute_spearman_rank(x, y)
        assert rho == 0.0
        assert p == 1.0


class TestCorrelationReport:
    def test_empty_report(self):
        report = compute_correlation_report([])
        assert isinstance(report, CorrelationReport)
        assert not report.passed

    def test_single_score(self):
        scores = [RoundScore(
            round_id=1,
            automated_scores={"correctness": 80.0, "testing": 75.0},
            human_scores=[{"correctness": 82.0, "testing": 73.0}],
        )]
        report = compute_correlation_report(scores)
        assert any(r.sample_count > 0 for r in report.results)

    def test_multiple_scores(self):
        scores = [
            RoundScore(i, {"correctness": 70 + i * 5, "testing": 60 + i * 3},
                       [{"correctness": 68 + i * 5, "testing": 62 + i * 3}])
            for i in range(10)
        ]
        report = compute_correlation_report(scores)
        assert len(report.results) == 2
        for r in report.results:
            assert r.sample_count == 10

    def test_missing_dimension(self):
        scores = [
            RoundScore(1, {"correctness": 80.0}, [{"correctness": 82.0}]),
            RoundScore(2, {"correctness": 75.0, "testing": 70.0}, [{"correctness": 77.0}]),
        ]
        report = compute_correlation_report(scores)
        assert any(r.dimension == "correctness" for r in report.results)

    def test_report_to_dict(self):
        report = CorrelationReport(passed=True, overall_spearman=0.85)
        d = report.to_dict()
        assert d["passed"] is True
        assert d["overall_spearman"] == 0.85
