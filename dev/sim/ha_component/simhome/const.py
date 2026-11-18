"""Constants for the simhome integration."""

DOMAIN = "simhome"
PLATFORMS = ["binary_sensor", "climate", "cover", "device_tracker", "number", "sensor", "weather"]
# Loaded only when the scenario has appliances in that domain, so other runs start unchanged
APPLIANCE_PLATFORMS = ("fan", "humidifier", "switch")
OBSERVE_INTERVAL_S = 30.0
PERSIST_INTERVAL_S = 300.0
FLUSH_INTERVAL_S = 600.0
# Domains whose HA state the observer records for checks (RoomMind ventilation, #267)
OBSERVED_STATE_DOMAINS = ("input_boolean", "fan")
