"""Tests for pycradlewise.models."""

import pytest

from pycradlewise.models import CradlewiseCradle, SleepAnalytics


class TestCradlewiseCradle:
    """Tests for the CradlewiseCradle dataclass."""

    def test_defaults(self):
        cradle = CradlewiseCradle(cradle_id="c1")
        assert cradle.cradle_id == "c1"
        assert cradle.baby_id is None
        assert cradle.baby_name is None
        assert cradle.state == {}
        assert cradle.online is False

    def test_baby_state_properties(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.baby_present is True
        assert cradle.baby_sleep_state == "sleeping"
        assert cradle.baby_needs_attention is False
        assert cradle.baby_needs_help is False
        assert cradle.is_crib_helping is True
        assert cradle.loud_sound_detected is False

    def test_baby_present_inference(self):
        # Case 1: Explicitly False, but sleep phase is 'awake'
        cradle = CradlewiseCradle(cradle_id="c1", state={"baby_present": False, "baby_sleep_state": "awake"})
        assert cradle.baby_present is True

        # Case 2: Missing flag, but sleep phase is numeric (1 = awake)
        cradle = CradlewiseCradle(cradle_id="c1", state={"babySleepPhase": "1"})
        assert cradle.baby_present is True

        # Case 3: Explicitly False, and sleep phase is 'away'
        cradle = CradlewiseCradle(cradle_id="c1", state={"baby_present": False, "babySleepPhase": "0"})
        assert cradle.baby_present is False

        # Case 4: Explicitly False, and phase is 'unknown'
        cradle = CradlewiseCradle(cradle_id="c1", state={"baby_present": False})
        assert cradle.baby_present is False

    def test_mode_properties(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.cradle_mode == "Normal"
        assert cradle.bounce_mode == "auto"
        assert cradle.bounce_setting == "medium"

    def test_actuator_properties(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.actuator == {"on": True, "amplitude": 3, "style": "gentle", "duration": 120}
        assert cradle.bouncing is True
        assert cradle.bounce_amplitude == 3

    def test_actuator_missing(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={})
        assert cradle.actuator == {}
        assert cradle.bouncing is None
        assert cradle.bounce_amplitude is None

    def test_music_properties(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.music_playing is True
        assert cradle.music_volume == 5
        assert cradle.music_mood == "calm"

    def test_music_missing(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={})
        assert cradle.music == {}
        assert cradle.music_playing is None
        assert cradle.music_volume is None
        assert cradle.music_mood == "None"

    def test_light_properties(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.light_on is True
        assert cradle.light_intensity == 40

    def test_light_missing(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={})
        assert cradle.light == {}
        assert cradle.light_on is False
        assert cradle.light_intensity == 0

    def test_schedule_properties(self, sample_shadow_state):
        analytics = SleepAnalytics(
            last_nap_start="2026-03-16T00:30:00Z",
            last_nap_end="2026-03-16T07:00:00Z"
        )
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state, analytics=analytics)
        assert cradle.sleep_time == "2026-03-16T00:30:00Z"
        assert cradle.wake_up_time == "2026-03-16T07:00:00Z"

    def test_sleep_phase_raw_from_v2(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.sleep_phase_raw == 4

    def test_sleep_phase_raw_from_string(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={"babySleepPhase": "2"})
        assert cradle.sleep_phase_raw == 2

    def test_sleep_phase_raw_missing(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={})
        assert cradle.sleep_phase_raw is None

    def test_sleep_phase_raw_non_numeric(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={"babySleepPhase": "unknown"})
        assert cradle.sleep_phase_raw is None
        assert cradle.sleep_phase_name == "Unknown"

    def test_sleep_phase_name_mapped(self):
        for val, expected in [(0, "Away"), (1, "Awake"), (2, "Stirring"), (4, "Sleep")]:
            cradle = CradlewiseCradle(cradle_id="c1", state={"babySleepPhaseV2": {"eventValue": val}})
            assert cradle.sleep_phase_name == expected

    def test_sleep_phase_name_unknown_int(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={"babySleepPhaseV2": {"eventValue": 99}})
        assert cradle.sleep_phase_name == "Unknown (99)"

    def test_update_state_merges_dicts(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.music_volume == 5
        cradle.update_state({"music": {"volume": 10}})
        assert cradle.music_volume == 10
        # Other music keys preserved
        assert cradle.music_playing is True

    def test_update_state_replaces_scalars(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        cradle.update_state({"babySleepPhaseV2": {"eventValue": 0}, "babyPresent": False})
        assert cradle.baby_present is False

    def test_update_state_adds_new_keys(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={})
        cradle.update_state({"babyPresent": True, "mode": "Crib"})
        assert cradle.baby_present is True
        assert cradle.cradle_mode == "Crib"

    def test_amplitude_int_conversion(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={"actuator": {"amplitude": 3.7}})
        assert cradle.bounce_amplitude == 3

    def test_volume_int_conversion(self):
        cradle = CradlewiseCradle(cradle_id="c1", state={"music": {"volume": 8.0}})
        assert cradle.music_volume == 8

    def test_schedule_window_and_effectiveness(self, sample_shadow_state):
        cradle = CradlewiseCradle(cradle_id="c1", state=sample_shadow_state)
        assert cradle.inside_sleep_schedule is True
        assert cradle.inside_soothing_window is False
        assert cradle.rocking_not_effective is False

        # Test snake_case fallback
        cradle_snake = CradlewiseCradle(
            cradle_id="c1",
            state={
                "inside_sleep_schedule": False,
                "inside_soothing_window": True,
                "rocking_not_effective": True,
            }
        )
        assert cradle_snake.inside_sleep_schedule is False
        assert cradle_snake.inside_soothing_window is True
        assert cradle_snake.rocking_not_effective is True


class TestSleepAnalytics:
    """Tests for the SleepAnalytics dataclass."""

    def test_defaults(self):
        a = SleepAnalytics()
        assert a.total_sleep_minutes == 0
        assert a.total_awake_minutes == 0
        assert a.total_soothe_count == 0
        assert a.nap_count == 0
        assert a.longest_nap_minutes == 0
        assert a.last_nap_start is None
        assert a.last_nap_end is None
        assert a.last_event_time is None
        assert a.last_event_value is None
        assert a.events == []

    def test_mutable_events(self):
        a = SleepAnalytics()
        b = SleepAnalytics()
        a.events.append({"test": 1})
        assert b.events == []
