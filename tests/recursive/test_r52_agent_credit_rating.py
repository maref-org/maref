from __future__ import annotations

from maref.recursive.agent_credit_rating import (
    DIMENSION_WEIGHTS,
    AgentCreditRatingSystem,
    AgentCreditReport,
    CreditRating,
    RatingDimension,
)


class TestCreditRating:
    def test_all_eight_levels(self):
        ratings = list(CreditRating)
        assert len(ratings) == 8

    def test_numeric_values(self):
        assert CreditRating.AAA.numeric_value == 8
        assert CreditRating.AA.numeric_value == 7
        assert CreditRating.A.numeric_value == 6
        assert CreditRating.BBB.numeric_value == 5
        assert CreditRating.BB.numeric_value == 4
        assert CreditRating.B.numeric_value == 3
        assert CreditRating.C.numeric_value == 2
        assert CreditRating.D.numeric_value == 1

    def test_trust_floors(self):
        assert CreditRating.AAA.trust_floor >= 0.85
        assert CreditRating.A.trust_floor >= 0.65
        assert CreditRating.D.trust_floor == 0.0

    def test_allowed_evolution(self):
        assert CreditRating.AAA.allowed_evolution
        assert CreditRating.BBB.allowed_evolution
        assert not CreditRating.B.allowed_evolution
        assert not CreditRating.D.allowed_evolution

    def test_requires_human_review(self):
        assert CreditRating.B.requires_human_review
        assert CreditRating.D.requires_human_review
        assert not CreditRating.AAA.requires_human_review
        assert not CreditRating.A.requires_human_review

    def test_next_up(self):
        assert CreditRating.D.next_up() == CreditRating.C
        assert CreditRating.C.next_up() == CreditRating.B
        assert CreditRating.BB.next_up() == CreditRating.BBB
        assert CreditRating.AAA.next_up() == CreditRating.AAA

    def test_next_down(self):
        assert CreditRating.AAA.next_down() == CreditRating.AA
        assert CreditRating.A.next_down() == CreditRating.BBB
        assert CreditRating.C.next_down() == CreditRating.D
        assert CreditRating.D.next_down() == CreditRating.D

    def test_rating_ordering(self):
        ratings = list(CreditRating)
        for i in range(len(ratings) - 1):
            assert ratings[i].numeric_value > ratings[i + 1].numeric_value


class TestAgentCreditRatingSystemInit:
    def test_default_init_rating_b(self):
        system = AgentCreditRatingSystem("agent_1")
        assert system.current_rating == CreditRating.B

    def test_init_with_registration_time(self):
        import time
        now = time.time()
        system = AgentCreditRatingSystem("agent_1", registered_at=now)
        assert system.survival_days < 0.01


class TestDimensionScoring:
    def test_update_and_get_dimension(self):
        system = AgentCreditRatingSystem("agent_1")
        system.update_dimension(RatingDimension.TASK_COMPLETION, 0.85)
        score = system.get_dimension_score(RatingDimension.TASK_COMPLETION)
        assert score > 0.8

    def test_multiple_updates_converge(self):
        system = AgentCreditRatingSystem("agent_1")
        for _ in range(20):
            system.update_dimension(RatingDimension.EVOLUTION_STABILITY, 0.7)
        score = system.get_dimension_score(RatingDimension.EVOLUTION_STABILITY)
        assert 0.6 <= score <= 0.8

    def test_dimension_trend_improving(self):
        system = AgentCreditRatingSystem("agent_1")
        for _ in range(10):
            system.update_dimension(RatingDimension.TASK_COMPLETION, 0.5)
        for _ in range(5):
            system.update_dimension(RatingDimension.TASK_COMPLETION, 0.8)
        assert system.get_dimension_trend(RatingDimension.TASK_COMPLETION) == "improving"

    def test_dimension_trend_declining(self):
        system = AgentCreditRatingSystem("agent_1")
        for _ in range(10):
            system.update_dimension(RatingDimension.TASK_COMPLETION, 0.8)
        for _ in range(5):
            system.update_dimension(RatingDimension.TASK_COMPLETION, 0.5)
        assert system.get_dimension_trend(RatingDimension.TASK_COMPLETION) == "declining"

    def test_dimension_trend_stable(self):
        system = AgentCreditRatingSystem("agent_1")
        for _ in range(15):
            system.update_dimension(RatingDimension.SAFETY_COMPLIANCE, 0.6)
        assert system.get_dimension_trend(RatingDimension.SAFETY_COMPLIANCE) == "stable"

    def test_trend_few_points(self):
        system = AgentCreditRatingSystem("agent_1")
        system.update_dimension(RatingDimension.TASK_COMPLETION, 0.5)
        assert system.get_dimension_trend(RatingDimension.TASK_COMPLETION) == "stable"

    def test_dimension_clamped_to_range(self):
        system = AgentCreditRatingSystem("agent_1")
        system.update_dimension(RatingDimension.TASK_COMPLETION, -0.5)
        system.update_dimension(RatingDimension.TASK_COMPLETION, 1.5)
        score = system.get_dimension_score(RatingDimension.TASK_COMPLETION)
        assert 0.0 <= score <= 1.0


class TestOverallScore:
    def test_weight_sum_is_one(self):
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_five_dimensions(self):
        assert len(RatingDimension) == 5

    def test_all_high_scores_yield_high_overall(self):
        system = AgentCreditRatingSystem("agent_1")
        for dim in RatingDimension:
            for _ in range(20):
                system.update_dimension(dim, 0.95)
        overall = system.calculate_overall_score()
        assert overall > 0.85

    def test_mixed_scores(self):
        system = AgentCreditRatingSystem("agent_1")
        for _ in range(20):
            system.update_dimension(RatingDimension.TASK_COMPLETION, 0.9)
            system.update_dimension(RatingDimension.SAFETY_COMPLIANCE, 0.3)
            system.update_dimension(RatingDimension.EVOLUTION_STABILITY, 0.5)
            system.update_dimension(RatingDimension.COMMUNITY_EVALUATION, 0.5)
            system.update_dimension(RatingDimension.SURVIVAL_TIME, 0.5)
        overall = system.calculate_overall_score()
        assert 0.4 <= overall <= 0.8


class TestRatingEvaluation:
    def test_evaluate_no_change_without_data(self):
        system = AgentCreditRatingSystem("agent_1")
        result = system.evaluate_rating()
        assert result is None

    def test_upgrade_from_b_to_bb(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        for dim in RatingDimension:
            for _ in range(20):
                system.update_dimension(dim, 0.95)
        system.reset_cooldown_for_test()
        result = system.evaluate_rating()
        assert result is not None
        assert result.rating.numeric_value > CreditRating.B.numeric_value

    def test_upgrade_to_aaa(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=60)
        for dim in RatingDimension:
            for _ in range(30):
                system.update_dimension(dim, 0.99)
        system.reset_cooldown_for_test()
        system.evaluate_rating()
        system.evaluate_rating()
        system.evaluate_rating()
        system.reset_cooldown_for_test()
        system.evaluate_rating()
        assert system.current_rating.numeric_value >= CreditRating.BBB.numeric_value

    def test_downgrade_on_low_scores(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        for dim in RatingDimension:
            for _ in range(20):
                system.update_dimension(dim, 0.2)
        system.reset_cooldown_for_test()
        result = system.evaluate_rating()
        if result is not None:
            assert result.rating.numeric_value < CreditRating.B.numeric_value

    def test_cooldown_prevents_rapid_changes(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        for dim in RatingDimension:
            for _ in range(20):
                system.update_dimension(dim, 0.99)
        system.evaluate_rating()
        result2 = system.evaluate_rating()
        assert result2 is None

    def test_rating_for_score_mapping(self):
        system = AgentCreditRatingSystem("agent_1")
        assert system.get_rating_for_score(0.95) == CreditRating.AAA
        assert system.get_rating_for_score(0.75) == CreditRating.A
        assert system.get_rating_for_score(0.55) == CreditRating.BB
        assert system.get_rating_for_score(0.35) == CreditRating.C
        assert system.get_rating_for_score(0.15) == CreditRating.D


class TestCreditReport:
    def test_generate_report(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        for dim in RatingDimension:
            system.update_dimension(dim, 0.7)
        report = system.get_report()
        assert isinstance(report, AgentCreditReport)
        assert report.agent_id == "agent_1"
        assert report.current_rating in CreditRating
        assert len(report.dimensions) == 5

    def test_report_history_includes_initial(self):
        system = AgentCreditRatingSystem("agent_1")
        report = system.get_report()
        assert len(report.history) >= 1

    def test_report_to_dict(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        d = system.to_dict()
        assert "agent_id" in d
        assert "rating" in d
        assert "dimensions" in d
        assert "history" in d

    def test_survival_days_tracking(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        report = system.get_report()
        assert report.survival_days >= 29.0

    def test_consecutive_tracking(self):
        system = AgentCreditRatingSystem("agent_1")
        system.fast_forward_time(days=30)
        for dim in RatingDimension:
            for _ in range(20):
                system.update_dimension(dim, 0.95)
        system.reset_cooldown_for_test()
        system.evaluate_rating()
        report = system.get_report()
        assert report.total_rating_changes >= 1
