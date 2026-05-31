"""Cradlewise REST API client."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import aiohttp
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from .auth import CradlewiseAuth
from .exceptions import CradlewiseApiError
from .models import CradlewiseCradle, SleepAnalytics, Nap

_LOGGER = logging.getLogger(__name__)


class CradlewiseClient:
    """Async client for the Cradlewise REST API."""

    def __init__(self, auth: CradlewiseAuth) -> None:
        self._auth = auth
        self._cradles: dict[str, CradlewiseCradle] = {}
        self._analytics: dict[str, SleepAnalytics] = {}

    @property
    def auth(self) -> CradlewiseAuth:
        return self._auth

    def _sign_request(
        self, method: str, url: str, body: str | None = None
    ) -> dict[str, str]:
        """Sign a request with SigV4."""
        creds = self._auth.credentials
        if not creds:
            raise CradlewiseApiError("Not authenticated")
        parsed = urlparse(url)
        headers = {
            "Host": parsed.hostname,
            "Content-Type": "application/json",
        }
        request = AWSRequest(method=method, url=url, headers=headers, data=body or "")
        region = self._auth.app_config.cognito_region
        SigV4Auth(creds.aws, "execute-api", region).add_auth(request)
        return dict(request.headers)

    async def _api_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        """Make a signed API request."""
        await self._auth.ensure_valid()

        base_url = self._auth.app_config.api_base_url
        url = f"{base_url}{path}"
        if params:
            query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
            url = f"{url}?{query}"

        body_str = json.dumps(body) if body else None
        headers = await asyncio.to_thread(self._sign_request, method, url, body_str)

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url, headers=headers, data=body_str
            ) as resp:
                if resp.status in (401, 403):
                    await self._auth.authenticate()
                    headers = await asyncio.to_thread(
                        self._sign_request, method, url, body_str
                    )
                    async with session.request(
                        method, url, headers=headers, data=body_str
                    ) as retry_resp:
                        retry_resp.raise_for_status()
                        return await retry_resp.json()
                resp.raise_for_status()
                return await resp.json()

    # ── Account & discovery ──────────────────────────────────────────────

    async def get_baby_profiles(self) -> list[dict[str, Any]]:
        """Get baby profiles for the authenticated user."""
        data = await self._api_request(
            "GET", "/babyProfiles/forEmail", params={"email_id": self._auth.email}
        )
        if isinstance(data, dict) and "user_list" in data:
            return data["user_list"]
        if isinstance(data, list):
            return data
        return []

    async def get_cradles_for_baby(self, baby_id: int | str) -> list[dict[str, Any]]:
        """Get cradles paired with a specific baby."""
        data = await self._api_request(
            "GET", f"/babyProfiles/{baby_id}/cradles"
        )
        if isinstance(data, dict) and "cradle_list" in data:
            return data["cradle_list"]
        if isinstance(data, list):
            return data
        return []

    async def get_baby_profile(self, baby_id: str | int) -> dict[str, Any]:
        """Get full baby profile for a specific baby."""
        return await self._api_request("GET", f"/babyProfiles/{baby_id}")

    async def discover_cradles(self) -> dict[str, CradlewiseCradle]:
        """Discover all cradles linked to the account."""
        profiles = await self.get_baby_profiles()
        cradles: dict[str, CradlewiseCradle] = {}

        for profile_summary in profiles:
            baby_id = profile_summary.get("baby_id") or profile_summary.get("id")
            if not baby_id:
                continue

            day_start_time = None
            try:
                full_profile = await self.get_baby_profile(baby_id)
                day_start_time = full_profile.get("day_start_time")
                baby_name = full_profile.get("name") or profile_summary.get("name", "Baby")
            except Exception as err:
                _LOGGER.debug("Failed to fetch full profile for %s: %s", baby_id, err)
                baby_name = profile_summary.get("name", "Baby")

            cradle_list = await self.get_cradles_for_baby(baby_id)
            for cradle_data in cradle_list:
                cradle_id = cradle_data.get("cradle_id")
                if cradle_id and cradle_id not in cradles:
                    cradles[cradle_id] = CradlewiseCradle(
                        cradle_id=cradle_id,
                        baby_id=str(baby_id),
                        baby_name=baby_name,
                        day_start_time=day_start_time,
                        timezone=cradle_data.get("timezone"),
                        serial_number=cradle_data.get("serial_no") or cradle_data.get("serialNumber") or cradle_data.get("serial_number"),
                    )

        self._cradles = cradles
        return cradles

    # ── Cradle status & control ──────────────────────────────────────────

    async def get_cradle_state(self, cradle_id: str) -> dict[str, Any]:
        """Get the current state of a specific cradle."""
        return await self._api_request("GET", f"/cradles/{cradle_id}/state")

    async def get_online_status(self, cradle_id: str) -> dict[str, Any]:
        """Get the current online status of a specific cradle."""
        return await self._api_request("GET", f"/cradles/{cradle_id}/onlineStatus/v2")

    async def get_firmware_data(self, cradle_id: str) -> dict[str, Any]:
        """Get firmware information for a cradle."""
        return await self._api_request("GET", f"/cradles/{cradle_id}/firmwareData")

    async def update_cradle(self, cradle: CradlewiseCradle) -> None:
        """Fetch the latest state and online status for a cradle."""
        try:
            state = await self.get_cradle_state(cradle.cradle_id)
            cradle.update_state(state)
        except Exception as err:
            _LOGGER.debug("Failed to get state for %s: %s", cradle.cradle_id, err)

        try:
            status = await self.get_online_status(cradle.cradle_id)
            if "state_message" in status:
                msg = json.loads(status["state_message"])
                cradle.online = msg.get("state", {}).get("state") == 1
            else:
                cradle.online = status.get("status") == "online"
        except Exception:
            cradle.online = True

        try:
            fw_data = await self.get_firmware_data(cradle.cradle_id)
            cradle.firmware_version = fw_data.get("version") or fw_data.get("rootfs_version")
            if not cradle.serial_number:
                cradle.serial_number = (
                    fw_data.get("serial_no")
                    or fw_data.get("serialNumber")
                    or fw_data.get("serial_number")
                )
        except Exception:
            pass

    async def set_cradle_state(self, cradle_id: str, state: dict[str, Any]) -> None:
        """Update the cradle state via REST API."""
        await self._api_request("PUT", f"/cradles/{cradle_id}/state", body=state)

    # ── Sleep analytics ──────────────────────────────────────────────────

    async def get_day_metrics(
        self, baby_id: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """Get daily sleep metrics."""
        return await self._api_request(
            "GET",
            f"/sleep-analytics/{baby_id}/day-metrics",
            params={"start_time": start_time, "end_time": end_time},
        )

    async def get_weekly_metrics(
        self, baby_id: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """Get weekly sleep metrics aggregates."""
        return await self._api_request(
            "GET",
            f"/sleep-analytics/{baby_id}/weekly-sleep-metrics",
            params={"start_time": start_time, "end_time": end_time},
        )

    async def get_monthly_metrics(
        self, baby_id: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """Get monthly sleep metrics aggregates."""
        return await self._api_request(
            "GET",
            f"/sleep-analytics/{baby_id}/monthly-sleep-metrics",
            params={"start_time": start_time, "end_time": end_time},
        )

    async def get_sleep_events(
        self, baby_id: str, params: dict | None = None
    ) -> list[dict[str, Any]]:
        """Get recent sleep events."""
        data = await self._api_request(
            "GET", f"/babyProfiles/{baby_id}/eventsV3", params=params
        )
        if isinstance(data, dict) and "event_list" in data:
            return data["event_list"]
        if isinstance(data, list):
            return data
        return []

    async def get_status_timeline(
        self, baby_id: str, cradle_id: str, params: dict | None = None
    ) -> dict[str, Any]:
        """Get detailed status timeline for a cradle."""
        return await self._api_request(
            "GET", f"/babyProfiles/{baby_id}/status_timeline_v2/{cradle_id}", params=params
        )

    async def fetch_sleep_analytics(
        self, cradle: CradlewiseCradle
    ) -> SleepAnalytics:
        """Fetch raw sleep analytics for a cradle's baby."""
        analytics = SleepAnalytics()
        baby_id = cradle.baby_id
        if not baby_id:
            return analytics

        analytics.day_start_time = cradle.day_start_time

        try:
            try:
                tz = ZoneInfo(cradle.timezone or "UTC")
            except Exception:
                tz = timezone.utc

            try:
                sh, sm = map(int, (cradle.day_start_time or "09:00").split(":"))
            except (ValueError, TypeError):
                sh, sm = 9, 0

            now_local = datetime.now(tz)
            boundary_local = now_local.replace(hour=sh, minute=sm, second=0, microsecond=0)

            end_local = boundary_local + timedelta(days=1)
            start_local = end_local - timedelta(days=7)

            start_time = start_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            end_time = end_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            metrics_data = await self.get_day_metrics(baby_id, start_time, end_time)
            if isinstance(metrics_data, dict) and "metrics" in metrics_data:
                if metrics_data["metrics"]:
                    latest_metrics = metrics_data["metrics"][-1]
                    _process_day_metrics(analytics, latest_metrics)
        except Exception as err:
            _LOGGER.debug("Failed to fetch day metrics for %s: %s", baby_id, err)

        try:
            week_data = await self.get_weekly_metrics(baby_id, start_time, end_time)
            if isinstance(week_data, dict):
                _process_weekly_metrics(analytics, week_data)
        except Exception as err:
            _LOGGER.debug("Failed to fetch weekly metrics for %s: %s", baby_id, err)

        try:
            _LOGGER.debug("Fetching timeline for baby %s and cradle %s", baby_id, cradle.cradle_id)
            timeline_data = await self.get_status_timeline(baby_id, cradle.cradle_id, params={"limit": 10})
            if isinstance(timeline_data, dict) and "status_list" in timeline_data:
                events = timeline_data["status_list"]
                if events:
                    latest = events[0]
                    ts = latest.get("event_time")
                    if ts:
                        try:
                            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            analytics.last_event_time = dt.isoformat().replace("+00:00", "Z")
                        except (ValueError, TypeError, OSError):
                            analytics.last_event_time = str(ts)
                    analytics.last_event_value = latest.get("message") or "Status updated"
                    if analytics.last_event_value and "<>" in analytics.last_event_value:
                        analytics.last_event_value = analytics.last_event_value.replace("<>", cradle.baby_name or "Baby")
                else:
                    analytics.last_event_value = "No recent events"
            else:
                analytics.last_event_value = "Status unavailable"
        except Exception as err:
            analytics.last_event_value = "Error fetching status"
            _LOGGER.warning("Failed to fetch timeline for %s: %s", baby_id, err)

        self._analytics[baby_id] = analytics
        return analytics


def _process_day_metrics(
    analytics: SleepAnalytics, data: dict[str, Any]
) -> None:
    """Map raw day-metrics response to the model."""
    banners = data.get("banners", [])
    for banner in banners:
        b_type = banner.get("type")
        header = banner.get("header", "")
        b_data = banner.get("data", {})

        if b_type == "soothes":
            analytics.total_soothe_count = int(b_data.get("value", 0))
            analytics.sleep_saved = banner.get("subtext")
        elif b_type == "naps":
            analytics.nap_count = int(b_data.get("value", 0))
            for nap_data in b_data.get("naps", []):
                analytics.naps.append(
                    Nap(
                        title=nap_data.get("title"),
                        start_time=nap_data.get("start_time"),
                        end_time=nap_data.get("end_time"),
                        duration=nap_data.get("duration"),
                    )
                )
            if analytics.naps:
                # The API returns naps in chronological order; the last one is most recent.
                latest_nap = analytics.naps[-1]
                analytics.last_nap_start = latest_nap.start_time
                analytics.last_nap_end = latest_nap.end_time
        elif b_type == "info":
            if header == "RISE TIME":
                analytics.rise_time = b_data.get("display_value")
            elif header == "BEDTIME":
                analytics.bed_time = b_data.get("display_value")
            elif header == "TIME IN BED":
                analytics.time_in_bed = b_data.get("display_value")
            elif header == "LONGEST STRETCH":
                analytics.longest_stretch = b_data.get("display_value")
            elif header == "AWAKE IN BED":
                analytics.awake_in_bed = b_data.get("display_value")


def _process_weekly_metrics(
    analytics: SleepAnalytics, data: dict[str, Any]
) -> None:
    """Map raw weekly metrics response to the model."""
    gm = data.get("sleep_graph_metrics", {})
    analytics.baby_age_text = gm.get("age_banner_text")

    def _mins_to_display(mins: float | None) -> str | None:
        if mins is None:
            return None
        h = int(mins // 60)
        m = int(mins % 60)
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

    analytics.weekly_avg_sleep = _mins_to_display(gm.get("avg_sleep_in_mins"))
    analytics.weekly_avg_day_sleep = _mins_to_display(gm.get("avg_day_sleep_in_mins"))
    analytics.weekly_avg_night_sleep = _mins_to_display(gm.get("avg_night_sleep_in_mins"))

    nm = data.get("nap_planner_metrics", {})
    analytics.weekly_avg_nap_duration = _mins_to_display(nm.get("avg_nap_duration_in_mins"))
    analytics.weekly_avg_naps_per_day = nm.get("avg_naps_per_day")

    rm = data.get("rise_and_bed_time_metrics", {})
    analytics.weekly_avg_rise_time = rm.get("avg_rise_time")
    analytics.weekly_avg_bed_time = rm.get("avg_bed_time")

    lm = data.get("longest_stretch_metrics", {})
    analytics.weekly_avg_longest_stretch = lm.get("avg_longest_stretch_display_text")
