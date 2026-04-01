"""Tests for pycradlewise.client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses
from botocore.credentials import Credentials

from pycradlewise.auth import CradlewiseAuth, CradlewiseCredentials
from pycradlewise.bootstrap import AppConfig
from pycradlewise.client import CradlewiseClient, _process_events, _process_analytics_response
from pycradlewise.models import CradlewiseCradle, SleepAnalytics


@pytest.fixture
def mock_auth(app_config):
    auth = MagicMock(spec=CradlewiseAuth)
    auth.email = "test@example.com"
    auth.app_config = app_config
    auth.credentials = CradlewiseCredentials(
        cognito=MagicMock(),
        aws=Credentials("AKID", "SECRET", "TOKEN"),
    )
    auth.ensure_valid = AsyncMock(return_value=auth.credentials)
    auth.authenticate = AsyncMock(return_value=auth.credentials)
    return auth


@pytest.fixture
def client(mock_auth):
    return CradlewiseClient(mock_auth)


class TestCradlewiseClient:
    def test_init(self, mock_auth):
        client = CradlewiseClient(mock_auth)
        assert client.auth is mock_auth

    @pytest.mark.asyncio
    async def test_discover_cradles(self, client, mock_auth, sample_baby_profiles):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(
                f"{base}/babyProfiles/forEmail?email_id=test%40example.com",
                payload={"user_list": sample_baby_profiles},
            )
            m.get(
                f"{base}/babyProfiles/123/cradles",
                payload={"cradle_list": [{"cradle_id": "cradle-aaa", "baby_id": 123}]},
            )
            m.get(
                f"{base}/babyProfiles/456/cradles",
                payload={"cradle_list": [{"cradle_id": "cradle-bbb", "baby_id": 456}]},
            )
            cradles = await client.discover_cradles()

        assert len(cradles) == 2
        assert "cradle-aaa" in cradles
        assert "cradle-bbb" in cradles
        assert cradles["cradle-aaa"].baby_name == "Baby A"
        assert cradles["cradle-bbb"].baby_id == "456"

    @pytest.mark.asyncio
    async def test_discover_cradles_with_timezone(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        profiles = [{"baby_id": 99, "name": "Test"}]
        with aioresponses() as m:
            m.get(f"{base}/babyProfiles/forEmail?email_id=test%40example.com", payload={"user_list": profiles})
            m.get(
                f"{base}/babyProfiles/99/cradles",
                payload={"cradle_list": [{"cradle_id": "cradle-xyz", "timezone": "US/Pacific"}]},
            )
            cradles = await client.discover_cradles()

        assert "cradle-xyz" in cradles
        assert cradles["cradle-xyz"].timezone == "US/Pacific"

    @pytest.mark.asyncio
    async def test_discover_cradles_no_cradle_paired(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        profiles = [{"baby_id": 99, "name": "NoCradle"}]
        with aioresponses() as m:
            m.get(f"{base}/babyProfiles/forEmail?email_id=test%40example.com", payload={"user_list": profiles})
            m.get(f"{base}/babyProfiles/99/cradles", payload={"cradle_list": []})
            cradles = await client.discover_cradles()

        assert len(cradles) == 0

    @pytest.mark.asyncio
    async def test_get_cradle_state(self, client, mock_auth, sample_shadow_state):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/state", payload=sample_shadow_state)
            state = await client.get_cradle_state("c1")

        assert state["babyPresent"] is True

    @pytest.mark.asyncio
    async def test_get_cradle_online_status(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/onlineStatus/v2", payload={"online": True})
            status = await client.get_cradle_online_status("c1")

        assert status["online"] is True

    @pytest.mark.asyncio
    async def test_get_firmware_data(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/firmwareData", payload={"version": "1.2.3"})
            fw = await client.get_firmware_data("c1")

        assert fw["version"] == "1.2.3"

    @pytest.mark.asyncio
    async def test_update_cradle(self, client, mock_auth, sample_shadow_state):
        base = mock_auth.app_config.api_base_url
        cradle = CradlewiseCradle(cradle_id="c1")

        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/state", payload=sample_shadow_state)
            m.get(f"{base}/cradles/c1/onlineStatus/v2", payload={"online": True})
            m.get(f"{base}/cradles/c1/firmwareData", payload={"version": "2.0"})
            await client.update_cradle(cradle)

        assert cradle.online is True
        assert cradle.baby_present is True
        assert cradle.firmware_version == "2.0"

    @pytest.mark.asyncio
    async def test_update_cradle_offline(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        cradle = CradlewiseCradle(cradle_id="c1")

        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/state", exception=ConnectionError("timeout"))
            m.get(f"{base}/cradles/c1/onlineStatus/v2", exception=ConnectionError())
            m.get(f"{base}/cradles/c1/firmwareData", exception=ConnectionError())
            await client.update_cradle(cradle)

        assert cradle.online is False

    @pytest.mark.asyncio
    async def test_get_sleep_events(self, client, mock_auth, sample_sleep_events):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/babyProfiles/123/eventsV3", payload=sample_sleep_events)
            events = await client.get_sleep_events("123")

        assert len(events) == 7

    @pytest.mark.asyncio
    async def test_get_analytics(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/babyProfiles/123/analyticsV3?start_hour=0", payload={"total_sleep": 300})
            data = await client.get_analytics("123")

        assert data["total_sleep"] == 300

    @pytest.mark.asyncio
    async def test_fetch_sleep_analytics(self, client, mock_auth, sample_sleep_events):
        base = mock_auth.app_config.api_base_url
        cradle = CradlewiseCradle(cradle_id="c1", baby_id="123")

        with aioresponses() as m:
            m.get(f"{base}/babyProfiles/123/eventsV3", payload=sample_sleep_events)
            m.get(f"{base}/babyProfiles/123/analyticsV3?start_hour=0", payload={})
            analytics = await client.fetch_sleep_analytics(cradle)

        assert analytics.nap_count == 2
        assert analytics.last_event_value == "awake"

    @pytest.mark.asyncio
    async def test_fetch_sleep_analytics_no_baby(self, client):
        cradle = CradlewiseCradle(cradle_id="c1", baby_id=None)
        analytics = await client.fetch_sleep_analytics(cradle)
        assert analytics.nap_count == 0

    def test_get_cached_analytics(self, client):
        assert client.get_cached_analytics("123") is None

    @pytest.mark.asyncio
    async def test_api_request_retries_on_403(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/state", status=403)
            m.get(f"{base}/cradles/c1/state", payload={"mode": "Normal"})
            state = await client.get_cradle_state("c1")

        assert state["mode"] == "Normal"
        mock_auth.authenticate.assert_called_once()


class TestProcessEvents:
    def test_basic_nap_detection(self, sample_sleep_events):
        analytics = SleepAnalytics()
        _process_events(analytics, sample_sleep_events)

        # Stirring doesn't end a nap. So:
        # Nap 1: 00:30 (sleep) -> 02:00 (stirring, still napping) -> 02:05 (sleep) -> 04:00 (awake) = 210 min
        # Nap 2: 04:30 (sleep) -> 06:30 (awake) = 120 min
        assert analytics.nap_count == 2
        assert analytics.longest_nap_minutes == 210
        assert analytics.total_sleep_minutes == 330
        assert analytics.last_event_value == "awake"
        assert analytics.last_event_time == "2026-03-16T06:30:00Z"

    def test_empty_events(self):
        analytics = SleepAnalytics()
        _process_events(analytics, [])
        assert analytics.nap_count == 0
        assert analytics.total_sleep_minutes == 0

    def test_ongoing_nap(self):
        events = [
            {"event_time": "2026-03-16T00:00:00Z", "event_value": "4"},  # sleep, no end
        ]
        analytics = SleepAnalytics()
        _process_events(analytics, events)
        assert analytics.nap_count == 1
        assert analytics.last_nap_end is None
        assert analytics.total_sleep_minutes > 0

    def test_non_numeric_event_value(self):
        events = [
            {"event_time": "2026-03-16T00:00:00Z", "event_value": "unknown"},
        ]
        analytics = SleepAnalytics()
        _process_events(analytics, events)
        assert analytics.nap_count == 0
        assert analytics.last_event_value == "unknown"

    def test_soothe_count(self):
        events = [
            {"event_time": "2026-03-16T00:00:00Z", "event_value": "4", "soothe_count": 2},
            {"event_time": "2026-03-16T01:00:00Z", "event_value": "4", "soothe_count": 3},
            {"event_time": "2026-03-16T02:00:00Z", "event_value": "1"},
        ]
        analytics = SleepAnalytics()
        _process_events(analytics, events)
        assert analytics.total_soothe_count == 5

    def test_invalid_soothe_count(self):
        events = [
            {"event_time": "2026-03-16T00:00:00Z", "event_value": "4", "soothe_count": "invalid"},
            {"event_time": "2026-03-16T01:00:00Z", "event_value": "1"},
        ]
        analytics = SleepAnalytics()
        _process_events(analytics, events)
        assert analytics.total_soothe_count == 0

    def test_last_nap_start_end(self, sample_sleep_events):
        analytics = SleepAnalytics()
        _process_events(analytics, sample_sleep_events)
        assert analytics.last_nap_start == "2026-03-16T04:30:00Z"
        assert analytics.last_nap_end == "2026-03-16T06:30:00Z"

    def test_away_event(self):
        events = [
            {"event_time": "2026-03-16T00:00:00Z", "event_value": "4"},  # sleep
            {"event_time": "2026-03-16T01:00:00Z", "event_value": "0"},  # away
        ]
        analytics = SleepAnalytics()
        _process_events(analytics, events)
        assert analytics.nap_count == 1

    def test_invalid_timestamp(self):
        events = [
            {"event_time": "not-a-date", "event_value": "4"},
            {"event_time": "also-not-a-date", "event_value": "1"},
        ]
        analytics = SleepAnalytics()
        _process_events(analytics, events)
        # Should not crash
        assert analytics.nap_count == 1
        assert analytics.total_sleep_minutes == 0  # couldn't parse


class TestProcessAnalyticsResponse:
    def test_merges_server_data(self):
        analytics = SleepAnalytics()
        _process_analytics_response(analytics, {
            "total_sleep": 120,
            "total_awake": 60,
            "soothe_count": 5,
        })
        assert analytics.total_sleep_minutes == 120
        assert analytics.total_awake_minutes == 60
        assert analytics.total_soothe_count == 5

    def test_ignores_missing_keys(self):
        analytics = SleepAnalytics(total_sleep_minutes=100)
        _process_analytics_response(analytics, {"unrelated_key": 42})
        assert analytics.total_sleep_minutes == 100

    def test_handles_invalid_values(self):
        analytics = SleepAnalytics()
        _process_analytics_response(analytics, {
            "total_sleep": "not_a_number",
            "soothe_count": None,
        })
        assert analytics.total_sleep_minutes == 0
        assert analytics.total_soothe_count == 0
