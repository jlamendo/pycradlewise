"""Tests for pycradlewise.bootstrap."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses

from pycradlewise.bootstrap import (
    AppConfig,
    CONFIG_CACHE_VERSION,
    get_app_config,
    refresh_app_config,
    _extract_config_from_apk,
    _get_download_url,
    APKPURE_API,
)

from .conftest import AMPLIFY_CONFIG_JSON


class TestAppConfig:
    def test_from_amplify_json(self):
        config = AppConfig.from_amplify_json(AMPLIFY_CONFIG_JSON)
        assert config.cognito_user_pool_id == "us-east-1_testUserPool"
        assert config.cognito_app_client_id == "test-app-client-id"
        assert config.cognito_app_client_secret == "test-app-client-secret"
        assert config.cognito_identity_pool_id == "us-east-1:test-identity-pool-id"
        assert config.cognito_region == "us-east-1"
        assert config.api_base_url == "https://backend.test.com/prod-latest"
        assert config.iot_endpoint is None

    def test_from_amplify_json_with_iot_endpoint(self):
        config = AppConfig.from_amplify_json(
            AMPLIFY_CONFIG_JSON,
            iot_endpoint="abc123-ats.iot.us-east-1.amazonaws.com",
        )
        assert config.iot_endpoint == "abc123-ats.iot.us-east-1.amazonaws.com"

    def test_to_dict_roundtrip(self):
        original = AppConfig(
            cognito_user_pool_id="pool",
            cognito_app_client_id="client",
            cognito_app_client_secret="secret",
            cognito_identity_pool_id="identity",
            cognito_region="us-west-2",
            api_base_url="https://api.test.com",
            iot_endpoint="test-ats.iot.us-west-2.amazonaws.com",
        )
        data = original.to_dict()
        restored = AppConfig.from_dict(data)
        assert restored == original

    def test_to_dict_keys(self):
        config = AppConfig.from_amplify_json(AMPLIFY_CONFIG_JSON)
        d = config.to_dict()
        assert set(d.keys()) == {
            "_cache_version",
            "cognito_user_pool_id",
            "cognito_app_client_id",
            "cognito_app_client_secret",
            "cognito_identity_pool_id",
            "cognito_region",
            "api_base_url",
            "iot_endpoint",
        }


FAKE_IOT_ENDPOINT = "a2bby18test-ats.iot.us-east-1.amazonaws.com"


def _make_xapk_bytes(
    amplify_config: dict, iot_endpoint: str = FAKE_IOT_ENDPOINT
) -> bytes:
    """Build a fake XAPK containing a base APK with the given amplify config."""
    # Embed the IoT endpoint in a fake DEX file (simulates compiled Kotlin constant)
    dex_content = b"\x00\x00" + iot_endpoint.encode("ascii") + b"\x00\x00"

    apk_buf = io.BytesIO()
    with zipfile.ZipFile(apk_buf, "w") as apk_zip:
        apk_zip.writestr("res/raw/amplifyconfiguration.json", json.dumps(amplify_config))
        apk_zip.writestr("classes.dex", dex_content)
    apk_bytes = apk_buf.getvalue()

    xapk_buf = io.BytesIO()
    with zipfile.ZipFile(xapk_buf, "w") as xapk_zip:
        xapk_zip.writestr("com.cradlewise.nini.app.apk", apk_bytes)
        xapk_zip.writestr("config.en.apk", b"fake-lang-split")
    return xapk_buf.getvalue()


class TestGetAppConfig:
    @pytest.mark.asyncio
    async def test_returns_cached(self, tmp_path):
        cache_data = {
            "_cache_version": CONFIG_CACHE_VERSION,
            "cognito_user_pool_id": "cached-pool",
            "cognito_app_client_id": "cached-client",
            "cognito_app_client_secret": "cached-secret",
            "cognito_identity_pool_id": "cached-identity",
            "cognito_region": "us-east-1",
            "api_base_url": "https://cached.api.com",
            "iot_endpoint": "cached-ats.iot.us-east-1.amazonaws.com",
        }
        cache_file = tmp_path / "cradlewise_app_config.json"
        cache_file.write_text(json.dumps(cache_data))

        config = await get_app_config(cache_dir=tmp_path)
        assert config.cognito_user_pool_id == "cached-pool"
        assert config.iot_endpoint == "cached-ats.iot.us-east-1.amazonaws.com"

    @pytest.mark.asyncio
    async def test_stale_cache_version_triggers_redownload(self, tmp_path):
        cache_data = {
            "_cache_version": 0,
            "cognito_user_pool_id": "old-pool",
            "cognito_app_client_id": "old-client",
            "cognito_app_client_secret": "old-secret",
            "cognito_identity_pool_id": "old-identity",
            "cognito_region": "us-east-1",
            "api_base_url": "https://old.api.com",
        }
        cache_file = tmp_path / "cradlewise_app_config.json"
        cache_file.write_text(json.dumps(cache_data))

        with patch("pycradlewise.bootstrap._extract_config_from_apk") as mock_extract:
            mock_extract.return_value = AppConfig.from_amplify_json(
                AMPLIFY_CONFIG_JSON,
                iot_endpoint=FAKE_IOT_ENDPOINT,
            )
            config = await get_app_config(cache_dir=tmp_path)

        assert config.cognito_user_pool_id == "us-east-1_testUserPool"
        assert config.iot_endpoint == FAKE_IOT_ENDPOINT

    @pytest.mark.asyncio
    async def test_invalid_cache_triggers_download(self, tmp_path):
        cache_file = tmp_path / "cradlewise_app_config.json"
        cache_file.write_text("not valid json")

        with patch("pycradlewise.bootstrap._extract_config_from_apk") as mock_extract:
            mock_extract.return_value = AppConfig.from_amplify_json(AMPLIFY_CONFIG_JSON)
            config = await get_app_config(cache_dir=tmp_path)

        assert config.cognito_user_pool_id == "us-east-1_testUserPool"
        assert cache_file.exists()
        cached = json.loads(cache_file.read_text())
        assert cached["cognito_user_pool_id"] == "us-east-1_testUserPool"

    @pytest.mark.asyncio
    async def test_creates_cache_dir(self, tmp_path):
        cache_dir = tmp_path / "nonexistent" / "subdir"

        with patch("pycradlewise.bootstrap._extract_config_from_apk") as mock_extract:
            mock_extract.return_value = AppConfig.from_amplify_json(AMPLIFY_CONFIG_JSON)
            await get_app_config(cache_dir=cache_dir)

        assert cache_dir.exists()
        assert (cache_dir / "cradlewise_app_config.json").exists()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, tmp_path):
        cache_data = {
            "_cache_version": CONFIG_CACHE_VERSION,
            "cognito_user_pool_id": "cached-pool",
            "cognito_app_client_id": "cached-client",
            "cognito_app_client_secret": "cached-secret",
            "cognito_identity_pool_id": "cached-identity",
            "cognito_region": "us-east-1",
            "api_base_url": "https://cached.api.com",
            "iot_endpoint": "cached-ats.iot.us-east-1.amazonaws.com",
        }
        cache_file = tmp_path / "cradlewise_app_config.json"
        cache_file.write_text(json.dumps(cache_data))

        with patch("pycradlewise.bootstrap._extract_config_from_apk") as mock_extract:
            mock_extract.return_value = AppConfig.from_amplify_json(
                AMPLIFY_CONFIG_JSON,
                iot_endpoint=FAKE_IOT_ENDPOINT,
            )
            config = await refresh_app_config(cache_dir=tmp_path)

        # Should have downloaded fresh, not used cache
        mock_extract.assert_called_once()
        assert config.cognito_user_pool_id == "us-east-1_testUserPool"
        assert config.iot_endpoint == FAKE_IOT_ENDPOINT


class TestExtractConfig:
    @pytest.mark.asyncio
    async def test_extracts_from_xapk(self):
        xapk_bytes = _make_xapk_bytes(AMPLIFY_CONFIG_JSON)
        fake_dl_url = "https://download.pureapk.com/b/XAPK/test?k=123"

        with patch("pycradlewise.bootstrap._get_download_url", return_value=fake_dl_url):
            with aioresponses() as m:
                m.get(fake_dl_url, body=xapk_bytes)
                config = await _extract_config_from_apk()

        assert config.cognito_user_pool_id == "us-east-1_testUserPool"
        assert config.api_base_url == "https://backend.test.com/prod-latest"
        assert config.iot_endpoint == FAKE_IOT_ENDPOINT

    @pytest.mark.asyncio
    async def test_raises_on_missing_base_apk(self):
        xapk_buf = io.BytesIO()
        with zipfile.ZipFile(xapk_buf, "w") as z:
            z.writestr("config.en.apk", b"fake")
        xapk_bytes = xapk_buf.getvalue()

        with patch("pycradlewise.bootstrap._get_download_url", return_value="https://fake.url"):
            with aioresponses() as m:
                m.get("https://fake.url", body=xapk_bytes)
                with pytest.raises(RuntimeError, match="No base APK found"):
                    await _extract_config_from_apk()

    @pytest.mark.asyncio
    async def test_raises_on_missing_config_in_apk(self):
        apk_buf = io.BytesIO()
        with zipfile.ZipFile(apk_buf, "w") as z:
            z.writestr("classes.dex", b"fake")
        xapk_buf = io.BytesIO()
        with zipfile.ZipFile(xapk_buf, "w") as z:
            z.writestr("com.cradlewise.nini.app.apk", apk_buf.getvalue())
        xapk_bytes = xapk_buf.getvalue()

        with patch("pycradlewise.bootstrap._get_download_url", return_value="https://fake.url"):
            with aioresponses() as m:
                m.get("https://fake.url", body=xapk_bytes)
                with pytest.raises(RuntimeError, match="not found in APK"):
                    await _extract_config_from_apk()


class TestGetDownloadUrl:
    @pytest.mark.asyncio
    async def test_extracts_url_from_response(self):
        fake_url = b"https://download.pureapk.com/b/XAPK/dGVzdA==?_fn=test&k=abc123"
        fake_body = b"\x00\x00XAPKJ\x00\x00" + fake_url + b"\x00\x00more"

        with aioresponses() as m:
            m.get(
                f"{APKPURE_API}?hl=en-US&package_name=com.cradlewise.nini.app",
                body=fake_body,
            )
            url = await _get_download_url()
            assert url == fake_url.decode("ascii")

    @pytest.mark.asyncio
    async def test_raises_on_no_url_found(self):
        with aioresponses() as m:
            m.get(
                f"{APKPURE_API}?hl=en-US&package_name=com.cradlewise.nini.app",
                body=b"no urls here",
            )
            with pytest.raises(RuntimeError, match="Could not find download URL"):
                await _get_download_url()
