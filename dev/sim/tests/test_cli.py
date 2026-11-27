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


def test_until_cuts_the_scenario_and_says_what_it_skipped():
    from helpers import scenario

    from roommind_sim.scenario import load_scenario_dict

    data = scenario(
        {"wohnzimmer": {"floor_area_m2": 20}},
        timeline=[
            {"at": "+1d", "do": "mark", "label": "inside"},
            {"at": "+3d", "do": "mark", "label": "after"},
            {"at": "+12h", "do": "mark", "label": "early"},
        ],
        expect=[
            {"invariant": "target_never_empty"},
            {"check": "outdoor < 30", "at": "+1d"},
            {"check": "outdoor < 30", "at": "+5d"},
            {"check": "outdoor < 30"},
            {"metric": "room.in_band_pct", "room": "wohnzimmer", "min": 50},
        ],
    )
    scn = load_scenario_dict(data)
    partial = cli._cut_to(scn, 2 * 86400)
    assert partial == {"of_s": 10 * 86400, "skipped_actions": 1, "skipped_expectations": 3}
    assert scn.duration == 2 * 86400
    assert [t.args["label"] for t in scn.timeline] == ["early", "inside"]
    assert scn.expect == [{"invariant": "target_never_empty"}, {"check": "outdoor < 30", "at": "+1d"}]
    # What HA loads from scenario.json is the cut scenario
    loaded = load_scenario_dict(cli._scenario_json(scn))
    assert [t.args["label"] for t in loaded.timeline] == ["early", "inside"]
    assert loaded.expect == scn.expect
