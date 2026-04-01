# pycradlewise

Async Python client for the [Cradlewise Smart Crib](https://www.cradlewise.com/) API.

Supports REST API polling and real-time AWS IoT MQTT push updates for cradle state, sleep analytics, and device monitoring.

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
        print(f"  Humidity: {cradle.humidity}")

        # Fetch sleep analytics
        if cradle.baby_id:
            analytics = await client.fetch_sleep_analytics(cradle)
            print(f"  Total sleep: {analytics.total_sleep_minutes} min")
            print(f"  Soothes: {analytics.total_soothe_count}")

asyncio.run(main())
```

## Real-Time Updates (MQTT)

```python
from pycradlewise import CradlewiseMqtt

mqtt = CradlewiseMqtt()

def on_update(cradle_id: str, state: dict):
    print(f"Update from {cradle_id}: {state}")

await mqtt.connect(
    access_key=auth.credentials.access_key,
    secret_key=auth.credentials.secret_key,
    session_token=auth.credentials.session_token,
    cradle_ids=list(cradles.keys()),
    on_state_update=on_update,
)

# mqtt.available == True when connected
# Call mqtt.disconnect() to clean up
```

## API Reference

### Bootstrap

- `get_app_config(cache_dir=None)` — Download and cache Cradlewise app config (Cognito pool IDs, API endpoint). Only downloads once; subsequent calls read from cache.
- `AppConfig` — Dataclass: `cognito_user_pool_id`, `cognito_app_client_id`, `cognito_app_client_secret`, `cognito_identity_pool_id`, `cognito_region`, `api_base_url`

### Authentication

- `CradlewiseAuth(email, password, app_config)` — Create auth instance
- `await auth.authenticate()` — Cognito SRP login + AWS IAM credential exchange
- `await auth.ensure_valid()` — Re-authenticate if credentials expired
- `auth.credentials` — `CradlewiseCredentials` with `access_key`, `secret_key`, `session_token`

### Client

- `CradlewiseClient(auth)` — Create API client

**Discovery:**
- `await client.get_baby_profiles()` — Baby profiles for the account → `list[dict]`
- `await client.get_cradles_for_baby(baby_id)` — Cradles paired with a baby → `list[dict]`
- `await client.discover_cradles()` — All cradles with baby associations → `dict[str, CradlewiseCradle]`

**Cradle State:**
- `await client.update_cradle(cradle)` — Fetch and apply latest state, online status, and firmware
- `await client.get_cradle_state(cradle_id)` — Raw state dict
- `await client.get_cradle_online_status(cradle_id)` — Online status
- `await client.get_firmware_data(cradle_id)` — Firmware version

**Sleep Analytics:**
- `await client.fetch_sleep_analytics(cradle)` — Aggregated sleep data → `SleepAnalytics`
- `await client.get_sleep_events(baby_id)` — Raw sleep events
- `await client.get_analytics(baby_id)` — Raw analytics data

### Models

**`CradlewiseCradle`** — Represents a smart crib with computed properties from state:

| Property | Type | Description |
|----------|------|-------------|
| `cradle_id` | `str` | Unique cradle identifier |
| `baby_id` | `str?` | Associated baby ID |
| `baby_name` | `str?` | Baby's name |
| `online` | `bool` | Connection status |
| `firmware_version` | `str?` | Current firmware |
| `baby_present` | `bool?` | Baby detected in crib |
| `sleep_phase_name` | `str?` | Human-readable sleep phase (away/awake/stirring/sleep) |
| `baby_needs_attention` | `bool?` | Attention alert |
| `bouncing` | `bool?` | Rocking motor active |
| `bounce_amplitude` | `int?` | Rocking intensity |
| `music_playing` | `bool?` | Music/white noise active |
| `music_volume` | `int?` | Music volume level |
| `light_on` | `bool?` | Nightlight active |
| `light_intensity` | `int?` | Light brightness |
| `temperature` | `float?` | Room temperature |
| `humidity` | `float?` | Room humidity |
| `noise_level` | `float?` | Ambient noise level |
| `battery_life` | `int?` | Battery percentage |
| `charging` | `bool?` | Charging status |
| `cradle_mode` | `str?` | Operating mode |
| `update_state(dict)` | method | Merge partial MQTT delta |

**`SleepAnalytics`** — Aggregated sleep data:

| Field | Type | Description |
|-------|------|-------------|
| `total_sleep_minutes` | `int` | Total sleep time |
| `total_awake_minutes` | `int` | Total awake time |
| `total_soothe_count` | `int` | Number of soothing interventions |
| `nap_count` | `int` | Number of naps |
| `longest_nap_minutes` | `int` | Longest nap duration |
| `events` | `list[dict]` | Raw sleep event list |

### MQTT

- `CradlewiseMqtt()` — Create MQTT client (requires `awsiotsdk`)
- `await mqtt.connect(access_key, secret_key, session_token, cradle_ids, on_state_update)` — Connect and subscribe
- `await mqtt.reconnect(...)` — Reconnect with fresh credentials
- `await mqtt.disconnect()` — Disconnect
- `mqtt.available` — `bool`, connection status

### Exceptions

- `CradlewiseError` — Base exception
- `CradlewiseAuthError` — Authentication failures (bad credentials, expired tokens)
- `CradlewiseApiError` — API request failures (HTTP errors, malformed responses)

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
                    ┌───────────────┴───────────────┐
                    ↓                               ↓
            CradlewiseClient              CradlewiseMqtt
          (REST, SigV4-signed)        (AWS IoT WebSocket)
                    ↓                               ↓
          Cradle state, analytics        Real-time state deltas
```

The library auto-downloads and caches the Cradlewise Android app's Amplify config on first use, extracting the Cognito pool IDs needed for authentication. All REST API requests are signed with AWS SigV4 using temporary IAM credentials obtained through the Cognito identity pool.

## Dependencies

- `pycognito` — Cognito SRP authentication
- `boto3` — AWS IAM credential exchange
- `aiohttp` — Async HTTP client
- `awsiotsdk` — AWS IoT MQTT (optional, for real-time updates)

## License

MIT
