"""Data models for the Cradlewise API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import SLEEP_PHASE_MAP, SLEEP_STAGE_MAP


@dataclass
class CradlewiseCradle:
    """Represents a Cradlewise crib."""

    cradle_id: str
    baby_id: str | None = None
    baby_name: str | None = None
    day_start_time: str | None = None
    rise_time: str | None = None
    firmware_version: str | None = None
    timezone: str | None = None
    serial_number: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    online: bool = False
    analytics: SleepAnalytics | None = None

    @property
    def baby_present(self) -> bool:
        """Return True if the baby is in the crib."""
        # 1. Check explicit occupancy flags
        if bool(self.state.get("baby_present", self.state.get("babyPresent", False))):
            return True

        # 2. Infer presence from sleep phase if flags are missing/stale
        phase = self.sleep_phase_name.lower()
        return phase not in ("away", "unknown")

    @property
    def baby_sleep_state(self) -> str:
        return self.state.get("baby_sleep_state", self.state.get("babySleepState")) or "unknown"

    @property
    def baby_sleep_phase(self) -> str | None:
        """Return the current sleep phase name."""
        state = self.state.get("baby_sleep_state")
        if state:
            return state
        return self.state.get("babySleepPhase")

    @property
    def baby_needs_attention(self) -> bool:
        return bool(self.state.get("baby_needs_attention", self.state.get("babyNeedsAttention", False)))

    @property
    def baby_needs_help(self) -> bool:
        return bool(self.state.get("baby_needs_help", self.state.get("babyNeedsHelp", False)))

    @property
    def is_crib_helping(self) -> bool:
        """Return True if the crib is currently soothing."""
        # Primary indicator: motor is active
        if self.bouncing:
            return True
        # Secondary indicator: startRecipe is active
        if self.state.get("startRecipeEnabled"):
            return True
        # Fallback
        return bool(self.state.get("isCribHelping", False))

    @property
    def loud_sound_detected(self) -> bool:
        return bool(self.state.get("loud_sound_detected", self.state.get("loudSoundDetected", False)))

    @property
    def cradle_mode(self) -> str | None:
        return self.state.get("detectedCradleMode", self.state.get("mode"))

    @property
    def max_bounce_limit(self) -> int | None:
        """Maximum allowed bounce amplitude."""
        val = self.state.get("maxBounceLimit")
        return int(val) if val is not None else None

    @property
    def max_volume_limit(self) -> int | None:
        """Maximum allowed music volume."""
        val = self.state.get("maxVolumeLimit")
        return int(val) if val is not None else None

    @property
    def bounce_level(self) -> int | None:
        """Discrete bounce level (-1 to 4)."""
        val = self.state.get("bounceLevel")
        return int(val) if val is not None else None

    @property
    def music_level(self) -> int | None:
        """Discrete music level (-1 to 4)."""
        val = self.state.get("musicLevel")
        return int(val) if val is not None else None

    @property
    def bounce_mode(self) -> str | None:
        manual = self.state.get("bounce_manual")
        if manual is not None:
            return "MANUAL" if manual else "SMART"
        return self.state.get("bounceMode")

    @property
    def bounce_setting(self) -> str | None:
        return self.state.get("bounce_setting", self.state.get("bounceSetting"))

    @property
    def responsivity_setting(self) -> int | None:
        val = self.state.get("responsivity_setting", self.state.get("responsivitySetting"))
        return int(val) if val is not None else None

    @property
    def responsivity_level(self) -> str | None:
        """Return human readable responsivity level."""
        return self.state.get("responsivitySettingVerbose")

    @property
    def cry_sensitivity(self) -> int | None:
        val = self.state.get("crySensitivity")
        return int(val) if val is not None else None

    @property
    def cry_sensitivity_level(self) -> str | None:
        """Return human readable cry sensitivity level."""
        return self.state.get("crySensitivityVerbose")

    @property
    def music_mode(self) -> str | None:
        manual = self.state.get("music_manual")
        if manual is not None:
            return "MANUAL" if manual else "SMART"
        return self.state.get("musicMode")

    @property
    def actuator(self) -> dict[str, Any]:
        return self.state.get("actuator") or {}

    @property
    def bouncing(self) -> bool | None:
        return self.actuator.get("on")

    @property
    def bounce_amplitude(self) -> int | None:
        val = self.actuator.get("amplitude")
        return int(val) if val is not None else None

    @property
    def music(self) -> dict[str, Any]:
        return self.state.get("music") or {}

    @property
    def sound_synth(self) -> dict[str, Any]:
        return self.state.get("soundSynth") or {}

    @property
    def music_playing(self) -> bool | None:
        return self.music.get("play") or self.sound_synth.get("play")

    @property
    def music_volume(self) -> int | None:
        # Prefer soundSynth volume if it's playing, otherwise fallback to music
        if self.sound_synth.get("play"):
            val = self.sound_synth.get("volume")
        else:
            val = self.music.get("volume")
        return int(val) if val is not None else None

    @property
    def music_mood(self) -> str:
        return self.music.get("mood") or "None"

    @property
    def music_track(self) -> str:
        """Current track name from soundSynth."""
        return self.sound_synth.get("trackName") or "None"

    @property
    def light(self) -> dict[str, Any]:
        return self.state.get("light") or {}

    @property
    def light_on(self) -> bool:
        return bool(self.light.get("lightOn", False))

    @property
    def light_intensity(self) -> int:
        val = self.light.get("lightIntensity", self.light.get("light_intensity", 0))
        return int(val) if val is not None else 0

    @property
    def temperature(self) -> float | None:
        """Room temperature in Celsius."""
        return self.state.get("ambientTempInCelsius")

    @property
    def sleep_time(self) -> str | None:
        """Return the start time of the most recent sleep session."""
        if self.analytics and self.analytics.last_nap_start:
            return self.analytics.last_nap_start
        return None

    @property
    def wake_up_time(self) -> str | None:
        """Return the end time of the most recent sleep session (if not currently sleeping)."""
        if self.analytics and self.analytics.last_nap_end:
            return self.analytics.last_nap_end
        return None

    @property
    def sleep_phase_raw(self) -> int | None:
        """Raw sleep phase integer from shadow."""
        phase_v2 = self.state.get("babySleepPhaseV2")
        if isinstance(phase_v2, dict):
            return phase_v2.get("eventValue")
        val = self.state.get("babySleepPhase")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def sleep_phase_name(self) -> str:
        """Human-readable coarse sleep phase (Away, Awake, Stirring, Sleep)."""
        raw = self.sleep_phase_raw
        if raw is not None:
            return SLEEP_PHASE_MAP.get(raw, f"unknown ({raw})").replace("_", " ").title()

        val = self.state.get("baby_sleep_state") or self.state.get("babySleepState") or self.state.get("babySleepPhase")
        if val is not None:
            if isinstance(val, int):
                return SLEEP_PHASE_MAP.get(val, f"unknown ({val})").replace("_", " ").title()
            sleep_state = str(val).lower()
            if "unknown" in sleep_state:
                return "Unknown"
            if "sleep" in sleep_state:
                return "Sleep"
            if "stirring" in sleep_state:
                return "Stirring"
            if "away" in sleep_state:
                return "Away"
            return "Awake"
        return "Unknown"

    @property
    def sleep_stage_name(self) -> str:
        """Human-readable granular sleep stage (Deep Sleep, Light Sleep, Quiet Awake, etc.)."""
        val = self.state.get("baby_sleep_state") or self.state.get("babySleepState")
        if val is not None:
            if isinstance(val, int):
                return SLEEP_STAGE_MAP.get(val, f"unknown ({val})").replace("_", " ").title()
            return str(val).replace("_", " ").title()

        raw = self.sleep_phase_raw
        if raw is not None:
            return SLEEP_STAGE_MAP.get(raw, f"unknown ({raw})").replace("_", " ").title()
        return "unknown"

    @property
    def auto_mode_lock_on(self) -> bool:
        return bool(self.state.get("autoModeLockOn", False))

    @property
    def auto_mode_lock_duration(self) -> int | None:
        val = self.state.get("autoModeLockDuration")
        return int(val) if val is not None else None

    @property
    def start_recipe_on(self) -> bool:
        return bool(self.state.get("startRecipeEnabled", False))

    @property
    def start_recipe_lock_duration(self) -> int | None:
        val = self.state.get("startRecipeLockDuration")
        return int(val) if val is not None else None

    @property
    def start_recipe_bounce_level(self) -> int | None:
        val = self.state.get("startRecipeBounceLevel")
        return int(val) if val is not None else None

    @property
    def start_recipe_music_level(self) -> int | None:
        val = self.state.get("startRecipeMusicLevel")
        return int(val) if val is not None else None

    @property
    def keep_bounce_on_during_sleep(self) -> bool:
        return bool(self.state.get("keepBounceOnDuringSleep", False))

    @property
    def keep_bounce_on_during_sleep_level(self) -> int | None:
        val = self.state.get("keepBounceOnDuringSleepLevel")
        return int(val) if val is not None else None

    @property
    def keep_music_on_during_sleep(self) -> bool:
        return bool(self.state.get("keepMusicOnDuringSleep", False))

    @property
    def keep_music_on_during_sleep_level(self) -> int | None:
        val = self.state.get("keepMusicOnDuringSleepLevel")
        return int(val) if val is not None else None

    @property
    def inside_sleep_schedule(self) -> bool:
        return bool(self.state.get("inside_sleep_schedule", self.state.get("insideSleepSchedule", False)))

    @property
    def inside_soothing_window(self) -> bool:
        return bool(self.state.get("inside_soothing_window", self.state.get("insideSoothingWindow", False)))

    @property
    def rocking_not_effective(self) -> bool:
        return bool(self.state.get("rocking_not_effective", self.state.get("rockingNotEffective", False)))

    def update_state(self, new_state: dict[str, Any]) -> None:
        """Merge partial state update (from MQTT delta)."""
        for key, value in new_state.items():
            if isinstance(value, dict) and isinstance(self.state.get(key), dict):
                self.state[key].update(value)
            else:
                self.state[key] = value


@dataclass
class Nap:
    """Represents a single nap session."""

    title: str
    start_time: str
    end_time: str
    duration: str


@dataclass
class SleepAnalytics:
    """Aggregated sleep analytics for a baby."""

    total_sleep_minutes: int = 0
    total_awake_minutes: int = 0
    total_soothe_count: int = 0
    nap_count: int = 0
    day_start_time: str | None = None
    rise_time: str | None = None
    bed_time: str | None = None
    time_in_bed: str | None = None
    longest_stretch: str | None = None
    awake_in_bed: str | None = None
    sleep_saved: str | None = None
    naps: list[Nap] = field(default_factory=list)
    # Weekly aggregates
    weekly_avg_sleep: str | None = None
    weekly_avg_day_sleep: str | None = None
    weekly_avg_night_sleep: str | None = None
    weekly_avg_nap_duration: str | None = None
    weekly_avg_naps_per_day: float | None = None
    weekly_avg_rise_time: str | None = None
    weekly_avg_bed_time: str | None = None
    weekly_avg_longest_stretch: str | None = None
    baby_age_text: str | None = None
    longest_nap_minutes: int = 0
    last_nap_start: str | None = None
    last_nap_end: str | None = None
    last_event_time: str | None = None
    last_event_value: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
