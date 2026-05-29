"""Constants for the Cradlewise API."""

# Sleep phase mapping (from APK Constants.java babySleepPhaseMap)
SLEEP_PHASE_MAP: dict[int, str] = {
    0: "away",
    1: "awake",
    2: "stirring",
    3: "stirring",
    4: "sleep",
    5: "sleep",
    6: "stirring",
}

# Detailed sleep stage mapping (granular event name)
SLEEP_STAGE_MAP: dict[int, str] = {
    0: "baby_not_present",
    1: "agitated",
    2: "active_awake",
    3: "quite_awake",
    4: "light_sleep",
    5: "deep_sleep",
    6: "stirring",
}
