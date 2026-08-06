from __future__ import annotations

from unittest import mock

import pytest

from maref.evolution.__main__ import build_parser


class TestBuildParser:
    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.output_dir == "./evolution_results/"
        assert args.rounds == 200
        assert args.resume_from is None
        assert args.resume_round == 0
        assert args.verbose is False

    def test_dry_run(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_output_dir(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--output-dir", "/tmp/out"])
        assert args.output_dir == "/tmp/out"

    def test_rounds(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--rounds", "100"])
        assert args.rounds == 100

    def test_resume(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--resume-from", "c2", "--resume-round", "10"])
        assert args.resume_from == "c2"
        assert args.resume_round == 10

    def test_verbose(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True


class TestMain:
    @pytest.mark.asyncio
    async def test_main_success_path(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                mock_args = mock.Mock()
                mock_args.dry_run = False
                mock_args.output_dir = "./evolution_results/"
                mock_args.rounds = 200
                mock_args.resume_from = None
                mock_args.resume_round = 0
                mock_args.verbose = False
                mock_parser.return_value.parse_args.return_value = mock_args
                mock_engine = mock_engine_cls.return_value
                mock_result = mock.Mock()
                mock_result.all_passed = True
                mock_result.summary.return_value = "PASSED"
                mock_engine.run = mock.AsyncMock(return_value=mock_result)
                from maref.evolution.__main__ import main
                exit_code = await main()
                assert exit_code == 0

    @pytest.mark.asyncio
    async def test_main_failure_path(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                mock_args = mock.Mock()
                mock_args.dry_run = False
                mock_args.output_dir = "./evolution_results/"
                mock_args.rounds = 200
                mock_args.resume_from = None
                mock_args.resume_round = 0
                mock_args.verbose = False
                mock_parser.return_value.parse_args.return_value = mock_args
                mock_engine = mock_engine_cls.return_value
                mock_result = mock.Mock()
                mock_result.all_passed = False
                mock_result.summary.return_value = "FAILED"
                mock_engine.run = mock.AsyncMock(return_value=mock_result)
                from maref.evolution.__main__ import main
                exit_code = await main()
                assert exit_code == 1

    @pytest.mark.asyncio
    async def test_main_dry_run_sets_one_round(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                mock_args = mock.Mock()
                mock_args.dry_run = True
                mock_args.output_dir = "./evolution_results/"
                mock_args.rounds = 200
                mock_args.resume_from = None
                mock_args.resume_round = 0
                mock_args.verbose = False
                mock_parser.return_value.parse_args.return_value = mock_args
                mock_engine = mock_engine_cls.return_value
                mock_result = mock.Mock()
                mock_result.all_passed = True
                mock_result.summary.return_value = "PASSED"
                mock_engine.run = mock.AsyncMock(return_value=mock_result)
                from maref.evolution.__main__ import main
                await main()
                config = mock_engine_cls.call_args[1]["config"]
                assert config.dry_run is True
                assert config.dry_run_rounds == 1

    @pytest.mark.asyncio
    async def test_main_fatal_exception(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                mock_args = mock.Mock()
                mock_args.dry_run = False
                mock_args.output_dir = "./evolution_results/"
                mock_args.rounds = 200
                mock_args.resume_from = None
                mock_args.resume_round = 0
                mock_args.verbose = False
                mock_parser.return_value.parse_args.return_value = mock_args
                mock_engine = mock_engine_cls.return_value
                mock_engine.run = mock.AsyncMock(side_effect=RuntimeError("Fatal error"))
                from maref.evolution.__main__ import main
                exit_code = await main()
                assert exit_code == 1

    @pytest.mark.asyncio
    async def test_main_keyboard_interrupt(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                mock_args = mock.Mock()
                mock_args.dry_run = False
                mock_args.output_dir = "./evolution_results/"
                mock_args.rounds = 200
                mock_args.resume_from = None
                mock_args.resume_round = 0
                mock_args.verbose = False
                mock_parser.return_value.parse_args.return_value = mock_args
                mock_engine = mock_engine_cls.return_value
                mock_result = mock.Mock()
                mock_result.all_passed = True
                mock_result.summary.return_value = "OK"
                mock_engine.run = mock.AsyncMock(side_effect=[KeyboardInterrupt(), mock_result])
                from maref.evolution.__main__ import main
                exit_code = await main()
                assert exit_code == 0
                mock_engine.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_resume_args(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                mock_args = mock.Mock()
                mock_args.dry_run = False
                mock_args.output_dir = "./evolution_results/"
                mock_args.rounds = 200
                mock_args.resume_from = "c2"
                mock_args.resume_round = 10
                mock_args.verbose = False
                mock_parser.return_value.parse_args.return_value = mock_args
                mock_engine = mock_engine_cls.return_value
                mock_result = mock.Mock()
                mock_result.all_passed = True
                mock_result.summary.return_value = "OK"
                mock_engine.run = mock.AsyncMock(return_value=mock_result)
                from maref.evolution.__main__ import main
                await main()
                config = mock_engine_cls.call_args[1]["config"]
                assert config.resume_from_cycle == "c2"
                assert config.resume_from_round == 10

    @pytest.mark.asyncio
    async def test_main_verbose_logging(self) -> None:
        with mock.patch("maref.evolution.__main__.build_parser") as mock_parser:
            with mock.patch("maref.evolution.__main__.RecursiveEvolutionEngine") as mock_engine_cls:
                with mock.patch("maref.evolution.__main__.logger") as mock_logger:
                    mock_args = mock.Mock()
                    mock_args.dry_run = False
                    mock_args.output_dir = "./evolution_results/"
                    mock_args.rounds = 200
                    mock_args.resume_from = None
                    mock_args.resume_round = 0
                    mock_args.verbose = True
                    mock_parser.return_value.parse_args.return_value = mock_args
                    mock_engine = mock_engine_cls.return_value
                    mock_result = mock.Mock()
                    mock_result.all_passed = True
                    mock_result.summary.return_value = "OK"
                    mock_engine.run = mock.AsyncMock(return_value=mock_result)
                    from maref.evolution.__main__ import main
                    await main()
                    assert mock_logger.info.call_count >= 1
