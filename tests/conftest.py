"""Shared test fixtures for pycradlewise."""

import pytest

from pycradlewise.bootstrap import AppConfig


@pytest.fixture
def app_config():
    """Return a test AppConfig."""
    return AppConfig(
        cognito_user_pool_id="us-east-1_testPool",
        cognito_app_client_id="test-client-id",
        cognito_app_client_secret="test-client-secret",
        cognito_identity_pool_id="us-east-1:test-identity-pool",
        cognito_region="us-east-1",
        api_base_url="https://backend.test.com/prod",
        iot_endpoint="test-endpoint-ats.iot.us-east-1.amazonaws.com",
    )


@pytest.fixture
def sample_shadow_state():
    """Return a realistic cradle shadow state."""
    return {
        "babyPresent": True,
        "babySleepState": "sleeping",
        "babySleepPhase": "4",
        "babySleepPhaseV2": {"eventValue": 4, "durationStartTime": "2026-03-16T01:00:00Z", "eventStartTime": "2026-03-16T00:30:00Z"},
        "babyNeedsAttention": False,
        "babyNeedsHelp": False,
        "isCribHelping": True,
        "loudSoundDetected": False,
        "insideSleepSchedule": True,
        "insideSoothingWindow": False,
        "rockingNotEffective": False,
        "mode": "Normal",
        "bounceMode": "auto",
        "bounceSetting": "medium",
        "responsivitySetting": "normal",
        "musicMode": "lullaby",
        "actuator": {"on": True, "amplitude": 3, "style": "gentle", "duration": 120},
        "music": {"play": True, "volume": 5, "mood": "calm", "repeat": True, "adaptiveVolume": True},
        "light": {"lightOn": True, "lightIntensity": 40, "indicatorBrightness": 10, "indicatorBrightnessMode": "auto"},
        "deviceStatus": {"batteryLife": 95, "charging": False, "supplyRemoved": False, "uptimeTotal": 86400},
        "sleepTime": "2026-03-16T00:30:00Z",
        "wakeUpTime": "2026-03-16T07:00:00Z",
        "keepMusicOnDuringSleep": True,
    }


@pytest.fixture
def sample_baby_profiles():
    """Return sample baby profile API response."""
    return [
        {
            "baby_id": "123",
            "name": "Baby A",
            "cradle_id": "cradle-aaa",
        },
        {
            "baby_id": "456",
            "name": "Baby B",
            "cradle_id": "cradle-bbb",
        },
    ]


@pytest.fixture
def sample_sleep_events():
    """Return sample sleep events from the API."""
    return [
        {"event_time": "2026-03-16T00:00:00Z", "event_value": "1"},  # awake
        {"event_time": "2026-03-16T00:30:00Z", "event_value": "4"},  # sleep
        {"event_time": "2026-03-16T02:00:00Z", "event_value": "2"},  # stirring
        {"event_time": "2026-03-16T02:05:00Z", "event_value": "4"},  # sleep
        {"event_time": "2026-03-16T04:00:00Z", "event_value": "1"},  # awake
        {"event_time": "2026-03-16T04:30:00Z", "event_value": "4"},  # sleep
        {"event_time": "2026-03-16T06:30:00Z", "event_value": "1"},  # awake
    ]


AMPLIFY_CONFIG_JSON = {
    "auth": {
        "plugins": {
            "awsCognitoAuthPlugin": {
                "IdentityManager": {"Default": {}},
                "CredentialsProvider": {
                    "CognitoIdentity": {
                        "Default": {
                            "PoolId": "us-east-1:test-identity-pool-id",
                            "Region": "us-east-1",
                        }
                    }
                },
                "CognitoUserPool": {
                    "Default": {
                        "PoolId": "us-east-1_testUserPool",
                        "AppClientId": "test-app-client-id",
                        "AppClientSecret": "test-app-client-secret",
                        "Region": "us-east-1",
                    }
                },
                "S3TransferUtility": {"Default": {"Bucket": "test-bucket", "Region": "us-east-1"}},
                "Auth": {"Default": {"authenticationFlowType": "USER_SRP_AUTH"}},
            }
        }
    },
    "storage": {"plugins": {"awsS3StoragePlugin": {"bucket": "test-bucket", "region": "us-east-1"}}},
    "api": {
        "plugins": {
            "awsAPIPlugin": {
                "yourApiName": {
                    "endpointType": "REST",
                    "endpoint": "https://backend.test.com/prod-latest",
                    "region": "us-east-1",
                    "authorizationType": "AWS_IAM",
                }
            }
        }
    },
}
