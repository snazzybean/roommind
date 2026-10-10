"""Scenario schema and loader."""

from .errors import ScenarioError
from .loader import load_scenario, load_scenario_dict
from .model import (
    DeviceSpec,
    Location,
    PersonSpec,
    RoomSpec,
    Scenario,
    SensorSpec,
    TimelineItem,
    WindowSpec,
)

__all__ = [
    "DeviceSpec",
    "Location",
    "PersonSpec",
    "RoomSpec",
    "Scenario",
    "ScenarioError",
    "SensorSpec",
    "TimelineItem",
    "WindowSpec",
    "load_scenario",
    "load_scenario_dict",
]
