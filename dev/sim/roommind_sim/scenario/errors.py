"""Scenario errors carry the path to the offending spot."""

from __future__ import annotations


class ScenarioError(ValueError):
    """Invalid scenario; ``where`` names the location (e.g. ``rooms.bad.devices[0]``)."""

    def __init__(self, message: str, where: str = "") -> None:
        self.where = where
        super().__init__(f"{where}: {message}" if where else message)
