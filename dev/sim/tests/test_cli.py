from roommind_sim import cli
from roommind_sim.paths import DEFAULT_HA_VERSION


def _suite_args(*argv: str):
    return cli._parser().parse_args(["suite", *argv])


def test_suite_passes_the_ha_version_to_every_run():
    args = _suite_args("--ha", "2026.11.0", "--roommind-src", "v1.8.0")
    assert cli._suite_run_args(args) == ["--roommind-src", "v1.8.0", "--ha", "2026.11.0"]


def test_suite_without_options_runs_the_default_ha():
    args = _suite_args()
    assert args.ha == DEFAULT_HA_VERSION
    assert cli._suite_run_args(args) == []


def test_ui_hover_action_points_at_the_element():
    from unittest.mock import MagicMock

    from roommind_sim.ui import _run_ui_action

    page = MagicMock()
    _run_ui_action(page, "hover:rs-analytics-chart ha-chart-base")
    page.locator.assert_called_once_with("rs-analytics-chart ha-chart-base")
    page.locator.return_value.first.hover.assert_called_once()


def test_ui_hover_action_takes_a_position():
    from unittest.mock import MagicMock

    from roommind_sim.ui import _run_ui_action

    page = MagicMock()
    _run_ui_action(page, "hover:ha-chart-base@200,120")
    page.locator.return_value.first.hover.assert_called_once_with(position={"x": 200.0, "y": 120.0})
