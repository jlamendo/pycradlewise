"""Bootstrap Cradlewise API config by extracting it from the published Android app.

Downloads the Cradlewise XAPK from APKPure, extracts the base APK,
and reads the AWS Amplify configuration (Cognito pool IDs, API endpoint, etc.).
The config is cached to disk so the download only happens once.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

PACKAGE_NAME = "com.cradlewise.nini.app"
APKPURE_API = "https://api.pureapk.com/m/v3/cms/app_version"
APKPURE_HEADERS = {
    "x-cv": "3172501",
    "x-sv": "29",
    "x-abis": "arm64-v8a",
    "x-gp": "1",
    "User-Agent": "APKPure/3.19.85 (Dalvik/2.1.0)",
}
CONFIG_PATH_IN_APK = "res/raw/amplifyconfiguration.json"
CACHE_FILENAME = "cradlewise_app_config.json"

# Expected signing certificate SHA-256 (Chigroo Labs / Cradlewise)
EXPECTED_CERT_SHA256 = (
    "79748B19F8761FA82829E33170AF58B7EEC4942689737B4E54B3EF0C60E546E5"
)


@dataclass
class AppConfig:
    """Cradlewise app configuration extracted from the APK."""

    cognito_user_pool_id: str
    cognito_app_client_id: str
    cognito_app_client_secret: str
    cognito_identity_pool_id: str
    cognito_region: str
    api_base_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "cognito_user_pool_id": self.cognito_user_pool_id,
            "cognito_app_client_id": self.cognito_app_client_id,
            "cognito_app_client_secret": self.cognito_app_client_secret,
            "cognito_identity_pool_id": self.cognito_identity_pool_id,
            "cognito_region": self.cognito_region,
            "api_base_url": self.api_base_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> AppConfig:
        return cls(
            cognito_user_pool_id=data["cognito_user_pool_id"],
            cognito_app_client_id=data["cognito_app_client_id"],
            cognito_app_client_secret=data["cognito_app_client_secret"],
            cognito_identity_pool_id=data["cognito_identity_pool_id"],
            cognito_region=data["cognito_region"],
            api_base_url=data["api_base_url"],
        )

    @classmethod
    def from_amplify_json(cls, raw: dict[str, Any]) -> AppConfig:
        """Parse the amplifyconfiguration.json format."""
        auth_plugin = raw["auth"]["plugins"]["awsCognitoAuthPlugin"]
        pool = auth_plugin["CognitoUserPool"]["Default"]
        identity = auth_plugin["CredentialsProvider"]["CognitoIdentity"]["Default"]
        api = raw["api"]["plugins"]["awsAPIPlugin"]["yourApiName"]

        return cls(
            cognito_user_pool_id=pool["PoolId"],
            cognito_app_client_id=pool["AppClientId"],
            cognito_app_client_secret=pool["AppClientSecret"],
            cognito_identity_pool_id=identity["PoolId"],
            cognito_region=pool["Region"],
            api_base_url=api["endpoint"],
        )


async def get_app_config(cache_dir: Path | None = None) -> AppConfig:
    """Get the Cradlewise app config, using cache if available.

    Args:
        cache_dir: Directory to cache the extracted config. If None,
                   defaults to ~/.pycradlewise/

    Returns:
        AppConfig with all Cognito and API settings.
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".pycradlewise"

    cache_file = cache_dir / CACHE_FILENAME

    # Try cache first
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            config = AppConfig.from_dict(data)
            _LOGGER.debug("Loaded app config from cache")
            return config
        except (json.JSONDecodeError, KeyError):
            _LOGGER.warning("Cached config is invalid, re-downloading")

    # Download and extract
    config = await _extract_config_from_apk()

    # Cache for next time
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(config.to_dict(), indent=2))
    _LOGGER.info("App config extracted and cached to %s", cache_file)

    return config


async def _extract_config_from_apk() -> AppConfig:
    """Download the Cradlewise APK and extract the Amplify config."""
    _LOGGER.info("Downloading Cradlewise app to extract API configuration...")

    # Step 1: Get XAPK download URL from APKPure
    download_url = await _get_download_url()

    # Step 2: Download the XAPK
    async with aiohttp.ClientSession() as session:
        async with session.get(
            download_url,
            headers={"User-Agent": APKPURE_HEADERS["User-Agent"]},
            ssl=False,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as resp:
            resp.raise_for_status()
            xapk_bytes = await resp.read()

    _LOGGER.info(
        "Downloaded %.1f MB, extracting config...", len(xapk_bytes) / 1024 / 1024
    )

    # Step 3: XAPK (zip) -> base APK (zip) -> amplifyconfiguration.json
    with zipfile.ZipFile(io.BytesIO(xapk_bytes)) as xapk:
        base_apk_names = [
            n
            for n in xapk.namelist()
            if n.endswith(".apk") and "config." not in n
        ]
        if not base_apk_names:
            raise RuntimeError("No base APK found in XAPK bundle")

        apk_bytes = xapk.read(base_apk_names[0])

    with zipfile.ZipFile(io.BytesIO(apk_bytes)) as apk:
        if CONFIG_PATH_IN_APK not in apk.namelist():
            raise RuntimeError(
                f"{CONFIG_PATH_IN_APK} not found in APK"
            )
        raw_config = json.loads(apk.read(CONFIG_PATH_IN_APK))

    return AppConfig.from_amplify_json(raw_config)


async def _get_download_url() -> str:
    """Query APKPure API for the latest XAPK download URL."""
    params = {"hl": "en-US", "package_name": PACKAGE_NAME}
    url = f"{APKPURE_API}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, headers=APKPURE_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            body = await resp.read()

    # Response is binary (protobuf). Extract XAPK download URLs.
    xapk_urls = re.findall(
        rb"(https://download\.pureapk\.com/b/XAPK/[A-Za-z0-9_=-]+\?[A-Za-z0-9_.&=%+-]+)",
        body,
    )

    if not xapk_urls:
        raise RuntimeError(
            "Could not find download URL in APKPure response. "
            "The API format may have changed."
        )

    return xapk_urls[0].decode("ascii")
