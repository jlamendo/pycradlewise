# pycradlewise

Async Python client for the [Cradlewise Smart Crib](https://www.cradlewise.com/) API.

Supports REST API polling for cradle state, sleep analytics, and device monitoring.

## Installation

```bash
pip install pycradlewise
```

## Quick Start

```python
import asyncio
from pycradlewise import CradlewiseAuth, CradlewiseClient, get_app_config

async def main():
    # Load API config (auto-downloaded from Cradlewise app, cached to disk)
    app_config = await get_app_config()

    # Authenticate
    auth = CradlewiseAuth(
        email="you@example.com",
        password="yourpassword",
        app_config=app_config,
    )
    await auth.authenticate()

    client = CradlewiseClient(auth)

    # Discover cribs linked to your account
    cradles = await client.discover_cradles()
    for cradle_id, cradle in cradles.items():
        print(f"{cradle.baby_name}: {cradle_id}")

        # Fetch latest state
        await client.update_cradle(cradle)
        print(f"  Online: {cradle.online}")
        print(f"  Sleep phase: {cradle.sleep_phase_name}")
        print(f"  Bouncing: {cradle.bouncing}")
        print(f"  Music: {cradle.music_playing}")
        print(f"  Light: {cradle.light_on}")
        print(f"  Temperature: {cradle.temperature}")

        # Fetch sleep analytics
        if cradle.baby_id:
            analytics = await client.fetch_sleep_analytics(cradle)
            print(f"  Total soothe count: {analytics.total_soothe_count}")

async def run():
    await main()

asyncio.run(run())
```

## API Reference

### Bootstrap

- `get_app_config(cache_dir=None)` — Download and cache Cradlewise app config (Cognito pool IDs, API endpoint). Only downloads once; subsequent calls read from cache.
- `AppConfig` — Dataclass: `cognito_user_pool_id`, `cognito_app_client_id`, `cognito_app_client_secret`, `cognito_identity_pool_id`, `cognito_region`, `api_base_url`

### Authentication

- `CradlewiseAuth(email, password, app_config)` — Create auth instance.
- `await auth.authenticate()` — Cognito SRP login + AWS IAM credential exchange.
- `await auth.ensure_valid()` — Re-authenticate if credentials expired.
- `auth.credentials` — `CradlewiseCredentials` with `access_key`, `secret_key`, `session_token`.

### Client

- `CradlewiseClient(auth)` — Create API client.

**Discovery:**
- `await client.get_baby_profiles()` — Baby profiles for the account → `list[dict]`
- `await client.get_cradles_for_baby(baby_id)` — Cradles paired with a baby → `list[dict]`
- `await client.discover_cradles()` — All cradles with baby associations → `dict[str, CradlewiseCradle]`

**Cradle State:**
- `await client.update_cradle(cradle)` — Fetch and apply latest state, online status, and firmware.
- `await client.get_cradle_state(cradle_id)` — Raw state dict.
- `await client.get_online_status(cradle_id)` — Online status.
- `await client.get_firmware_data(cradle_id)` — Firmware version.

**Sleep Analytics:**
- `await client.fetch_sleep_analytics(cradle)` — Aggregated sleep data → `SleepAnalytics`
- `await client.get_day_metrics(baby_id, start_time, end_time)` — Raw daily metrics.
- `await client.get_weekly_metrics(baby_id, start_time, end_time)` — Raw weekly metrics aggregates.
- `await client.get_monthly_metrics(baby_id, start_time, end_time)` — Raw monthly metrics aggregates.
- `await client.get_sleep_events(baby_id)` — Raw sleep events list.
- `await client.get_status_timeline(baby_id, cradle_id)` — Recent descriptive timeline events.

### Models

**`CradlewiseCradle`** — Represents a smart crib with computed properties:

| Property | Type | Description |
|----------|------|-------------|
| `cradle_id` | `str` | Unique cradle identifier |
| `baby_id` | `str?` | Associated baby ID |
| `baby_name` | `str?` | Baby's name |
| `online` | `bool` | Connection status |
| `firmware_version` | `str?` | Current firmware version |
| `baby_present` | `bool` | Baby detected in crib |
| `sleep_phase_name` | `str` | Coarse sleep phase name (Away, Awake, Stirring, Sleep, Unknown) |
| `sleep_stage_name` | `str` | Granular sleep stage name (Deep Sleep, Light Sleep, Quiet Awake, etc.) |
| `is_crib_helping` | `bool` | True if the crib is soothing (bouncing or running recipe) |
| `bouncing` | `bool?` | True if rocking motor is active |
| `bounce_amplitude` | `int?` | Rocking intensity amplitude |
| `music_playing` | `bool?` | True if music/white noise is active |
| `music_volume` | `int?` | Music volume level |
| `music_track` | `str` | Current music track name |
| `light_on` | `bool` | True if nightlight is active |
| `light_intensity` | `int` | Nightlight brightness |
| `temperature` | `float?`| Room temperature in Celsius |

**`SleepAnalytics`** — Aggregated sleep data:

| Field | Type | Description |
|-------|------|-------------|
| `total_soothe_count` | `int` | Number of soothing interventions |
| `sleep_saved` | `str?` | Subtext description of sleep duration saved |
| `nap_count` | `int` | Number of naps today |
| `rise_time` | `str?` | Display rising time |
| `bed_time` | `str?` | Display bedtime |
| `time_in_bed` | `str?` | Display time spent in bed |
| `longest_stretch` | `str?` | Display longest sleep stretch |
| `awake_in_bed` | `str?` | Display awake duration in bed |
| `weekly_avg_sleep` | `str?` | Display weekly average sleep time |
| `weekly_avg_day_sleep` | `str?` | Display weekly average day sleep time |
| `weekly_avg_night_sleep`| `str?`| Display weekly average night sleep time |
| `weekly_avg_nap_duration`| `str?`| Display weekly average nap duration |
| `weekly_avg_naps_per_day`| `float?`| Average naps per day over the week |
| `weekly_avg_rise_time` | `str?` | Average rise time over the week |
| `weekly_avg_bed_time` | `str?` | Average bedtime over the week |
| `weekly_avg_longest_stretch`| `str?`| Average longest stretch over the week |
| `baby_age_text` | `str?` | Current age banner text |
| `last_nap_start` | `str?` | ISO start time of the most recent nap |
| `last_nap_end` | `str?` | ISO end time of the most recent nap |
| `last_event_time` | `str?` | ISO timestamp of the last status update |
| `last_event_value` | `str?` | Value/Message of the last status update |

### Exceptions

- `CradlewiseError` — Base exception.
- `CradlewiseAuthError` — Authentication failures.
- `CradlewiseApiError` — API request failures.

## Architecture

```
Phone App → Cradlewise APK → amplifyconfiguration.json
                                    ↓
                              get_app_config()
                                    ↓
                            Cognito User Pool IDs
                                    ↓
                    CradlewiseAuth (Cognito SRP + IAM)
                                    ↓
                             CradlewiseClient
                           (REST, SigV4-signed)
                                    ↓
                         Cradle state & analytics
```

The library auto-downloads and caches the Cradlewise Android app's Amplify config on first use, extracting the Cognito pool IDs needed for authentication. All REST API requests are signed with AWS SigV4 using temporary IAM credentials obtained through the Cognito identity pool.

## Dependencies

- `pycognito` — Cognito SRP authentication
- `boto3` — AWS IAM credential exchange
- `aiohttp` — Async HTTP client

## License

MIT
