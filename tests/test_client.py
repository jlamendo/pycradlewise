"""Tests for pycradlewise.client."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aioresponses import aioresponses
from botocore.credentials import Credentials

from pycradlewise.auth import CradlewiseAuth, CradlewiseCredentials
from pycradlewise.client import (
    CradlewiseClient,
    _process_day_metrics,
    _process_weekly_metrics,
)
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
                f"{base}/babyProfiles/123",
                payload={"name": "Baby A", "day_start_time": "09:00"},
            )
            m.get(
                f"{base}/babyProfiles/456/cradles",
                payload={"cradle_list": [{"cradle_id": "cradle-bbb", "baby_id": 456}]},
            )
            m.get(
                f"{base}/babyProfiles/456",
                payload={"name": "Baby B", "day_start_time": "08:00"},
            )
            cradles = await client.discover_cradles()

        assert len(cradles) == 2
        assert "cradle-aaa" in cradles
        assert "cradle-bbb" in cradles
        assert cradles["cradle-aaa"].baby_name == "Baby A"
        assert cradles["cradle-aaa"].day_start_time == "09:00"

    @pytest.mark.asyncio
    async def test_get_cradle_state(self, client, mock_auth, sample_shadow_state):
        base = mock_auth.app_config.api_base_url
        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/state", payload=sample_shadow_state)
            state = await client.get_cradle_state("c1")

        assert state["babyPresent"] is True

    @pytest.mark.asyncio
    async def test_update_cradle(self, client, mock_auth, sample_shadow_state):
        base = mock_auth.app_config.api_base_url
        cradle = CradlewiseCradle(cradle_id="c1")

        with aioresponses() as m:
            m.get(f"{base}/cradles/c1/state", payload=sample_shadow_state)
            m.get(
                f"{base}/cradles/c1/onlineStatus/v2",
                payload={"state_message": '{"state": {"state": 1}}'},
            )
            await client.update_cradle(cradle)

        assert cradle.online is True
        assert cradle.baby_present is True

    @pytest.mark.asyncio
    async def test_fetch_sleep_analytics(self, client, mock_auth):
        base = mock_auth.app_config.api_base_url
        cradle = CradlewiseCradle(cradle_id="c1", baby_id="123", timezone="UTC")

        day_metrics = {
            "metrics": [
                {
                    "banners": [
                        {"type": "soothes", "data": {"value": 5}, "subtext": "2h saved"},
                        {
                            "type": "naps",
                            "data": {
                                "value": 2,
                                "naps": [
                                    {
                                        "title": "Nap 1",
                                        "start_time": "2026-03-16T10:00:00Z",
                                        "end_time": "2026-03-16T11:00:00Z",
                                    }
                                ],
                            },
                        },
                    ]
                }
            ]
        }

        timeline_data = {
            "status_list": [
                {
                    "event_time": 1773642600000,  # 2026-03-16T06:30:00Z
                    "message": "Baby woke up",
                }
            ]
        }

        import re
        with aioresponses() as m:
            m.get(
                re.compile(rf"^{base}/sleep-analytics/123/day-metrics"),
                payload=day_metrics,
                repeat=True,
            )
            m.get(
                re.compile(rf"^{base}/sleep-analytics/123/weekly-sleep-metrics"),
                payload={},
                repeat=True,
            )
            m.get(
                f"{base}/babyProfiles/123/status_timeline_v2/c1?limit=10",
                payload=timeline_data,
            )
            analytics = await client.fetch_sleep_analytics(cradle)

        assert analytics.total_soothe_count == 5
        assert analytics.nap_count == 2
        assert analytics.last_nap_start == "2026-03-16T10:00:00Z"
        assert analytics.last_event_value == "Baby woke up"
        assert analytics.last_event_time == "2026-03-16T06:30:00Z"


class TestProcessDayMetrics:
    def test_soothes_processing(self):
        analytics = SleepAnalytics()
        data = {
            "banners": [
                {"type": "soothes", "data": {"value": "10"}, "subtext": "1h 30m saved"}
            ]
        }
        _process_day_metrics(analytics, data)
        assert analytics.total_soothe_count == 10
        assert analytics.sleep_saved == "1h 30m saved"

    def test_naps_processing(self):
        analytics = SleepAnalytics()
        data = {
            "banners": [
                {
                    "type": "naps",
                    "data": {
                        "value": 3,
                        "naps": [
                            {
                                "title": "Nap 1",
                                "start_time": "2026-03-16T12:00:00Z",
                                "end_time": "2026-03-16T13:00:00Z",
                            },
                            {
                                "title": "Nap 2",
                                "start_time": "2026-03-16T15:00:00Z",
                                "end_time": "2026-03-16T16:00:00Z",
                            },
                        ],
                    },
                }
            ]
        }
        _process_day_metrics(analytics, data)
        assert analytics.nap_count == 3
        assert len(analytics.naps) == 2
        assert analytics.last_nap_start == "2026-03-16T15:00:00Z"

    def test_info_processing(self):
        analytics = SleepAnalytics()
        data = {
            "banners": [
                {"type": "info", "header": "RISE TIME", "data": {"display_value": "7:00 AM"}},
                {"type": "info", "header": "BEDTIME", "data": {"display_value": "8:30 PM"}},
            ]
        }
        _process_day_metrics(analytics, data)
        assert analytics.rise_time == "7:00 AM"
        assert analytics.bed_time == "8:30 PM"


class TestProcessWeeklyMetrics:
    def test_graph_metrics(self):
        analytics = SleepAnalytics()
        data = {
            "sleep_graph_metrics": {
                "avg_sleep_in_mins": 480,
                "age_banner_text": "6 months",
            }
        }
        _process_weekly_metrics(analytics, data)
        assert analytics.weekly_avg_sleep == "8h 0m"
        assert analytics.baby_age_text == "6 months"

    def test_nap_planner_metrics(self):
        analytics = SleepAnalytics()
        data = {
            "sleep_graph_metrics": {
                "avg_sleep_in_mins": 480,
                "age_banner_text": "6 months",
            },
            "nap_planner_metrics": {
                "avg_nap_duration_in_mins": 90,
                "avg_naps_per_day": 2.5,
            }
        }
        _process_weekly_metrics(analytics, data)
        assert analytics.weekly_avg_nap_duration == "1h 30m"
        assert analytics.weekly_avg_naps_per_day == 2.5
