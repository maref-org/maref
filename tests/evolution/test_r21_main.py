from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

from src.maref.evolution.__main__ import build_parser


class TestEvolutionMain:
    def test_build_parser_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.output_dir == "./evolution_results/"
        assert args.rounds == 200
        assert args.resume_from is None
        assert args.resume_round == 0
        assert args.verbose is False

    def test_build_parser_dry_run(self):
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_build_parser_output_dir(self):
        parser = build_parser()
        args = parser.parse_args(["--output-dir", "/tmp/evolve"])
        assert args.output_dir == "/tmp/evolve"

    def test_build_parser_rounds(self):
        parser = build_parser()
        args = parser.parse_args(["--rounds", "50"])
        assert args.rounds == 50

    def test_build_parser_resume(self):
        parser = build_parser()
        args = parser.parse_args(["--resume-from", "c2", "--resume-round", "10"])
        assert args.resume_from == "c2"
        assert args.resume_round == 10

    def test_build_parser_verbose(self):
        parser = build_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_success_path(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_result = MagicMock()
        mock_result.all_passed = True
        mock_result.summary.return_value = "Summary OK"

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_result)
        mock_engine_class.return_value = mock_engine

        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 0

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_failure_path(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_result = MagicMock()
        mock_result.all_passed = False
        mock_result.summary.return_value = "Summary FAIL"

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_result)
        mock_engine_class.return_value = mock_engine

        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 1

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_with_resume_args(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_result = MagicMock()
        mock_result.all_passed = True
        mock_result.summary.return_value = "Summary"

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_result)
        mock_engine_class.return_value = mock_engine

        mock_config = MagicMock()
        mock_config.max_total_rounds = 200
        mock_config.resume_from_cycle = None
        mock_config_class.return_value = mock_config

        test_args = ["prog", "--resume-from", "c3", "--resume-round", "5"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 0
            assert mock_config.resume_from_cycle == "c3"
            assert mock_config.resume_from_round == 5

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_fatal_exception(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(side_effect=RuntimeError("engine crash"))
        mock_engine_class.return_value = mock_engine

        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 1

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_keyboard_interrupt(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_result = MagicMock()
        mock_result.all_passed = True
        mock_result.summary.return_value = "Recovered"

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(side_effect=[KeyboardInterrupt(), mock_result])
        mock_engine_class.return_value = mock_engine
        mock_engine.stop = MagicMock()

        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 0

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_dry_run_sets_one_round(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_result = MagicMock()
        mock_result.all_passed = True
        mock_result.summary.return_value = "Dry run OK"

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_result)
        mock_engine_class.return_value = mock_engine

        mock_config = MagicMock()
        mock_config.dry_run = False
        mock_config_class.return_value = mock_config

        test_args = ["prog", "--dry-run"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 0
            assert mock_config.dry_run is True
            assert mock_config.dry_run_rounds == 1

    @patch("src.maref.evolution.__main__.RecursiveEvolutionEngine")
    @patch("src.maref.evolution.__main__.EvolutionConfig")
    def test_main_verbose_prints(self, mock_config_class, mock_engine_class):
        from src.maref.evolution.__main__ import main

        mock_result = MagicMock()
        mock_result.all_passed = True
        mock_result.summary.return_value = "Verbose OK"

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_result)
        mock_engine_class.return_value = mock_engine

        mock_config = MagicMock()
        mock_config.max_total_rounds = 200
        mock_config.resume_from_cycle = "c1"
        mock_config.resume_from_round = 0
        mock_config_class.return_value = mock_config

        test_args = ["prog", "--verbose", "--resume-from", "c1"]
        with patch.object(sys, "argv", test_args):
            import asyncio

            rc = asyncio.run(main())
            assert rc == 0
