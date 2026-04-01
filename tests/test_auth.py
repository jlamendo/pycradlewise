"""Tests for pycradlewise.auth."""

from unittest.mock import MagicMock, patch

import pytest

from pycradlewise.auth import CradlewiseAuth, CradlewiseCredentials
from pycradlewise.exceptions import CradlewiseAuthError


class TestCradlewiseCredentials:
    def test_properties(self):
        mock_cognito = MagicMock()
        mock_aws = MagicMock()
        mock_aws.access_key = "AKID"
        mock_aws.secret_key = "SECRET"
        mock_aws.token = "TOKEN"

        creds = CradlewiseCredentials(cognito=mock_cognito, aws=mock_aws)
        assert creds.access_key == "AKID"
        assert creds.secret_key == "SECRET"
        assert creds.session_token == "TOKEN"


class TestCradlewiseAuth:
    def test_init(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)
        assert auth.email == "test@example.com"
        assert auth.credentials is None
        assert auth.app_config is app_config

    @pytest.mark.asyncio
    async def test_authenticate_success(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)

        mock_cognito = MagicMock()
        mock_cognito.id_token = "fake-id-token"

        mock_creds = {
            "IdentityId": "us-east-1:fake-identity",
        }
        mock_creds_response = {
            "Credentials": {
                "AccessKeyId": "AKID",
                "SecretKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

        with patch.object(auth, "_cognito_auth", return_value=mock_cognito):
            with patch.object(auth, "_exchange_for_iam") as mock_exchange:
                from botocore.credentials import Credentials
                mock_exchange.return_value = Credentials("AKID", "SECRET", "TOKEN")
                result = await auth.authenticate()

        assert result is not None
        assert result.access_key == "AKID"
        assert auth.credentials is result

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, app_config):
        auth = CradlewiseAuth("test@example.com", "bad-password", app_config)

        with patch.object(auth, "_cognito_auth", side_effect=Exception("Invalid password")):
            with pytest.raises(CradlewiseAuthError, match="Authentication failed"):
                await auth.authenticate()

    @pytest.mark.asyncio
    async def test_ensure_valid_no_credentials(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)

        mock_cognito = MagicMock()
        from botocore.credentials import Credentials
        mock_creds = Credentials("AKID", "SECRET", "TOKEN")

        with patch.object(auth, "_cognito_auth", return_value=mock_cognito):
            with patch.object(auth, "_exchange_for_iam", return_value=mock_creds):
                result = await auth.ensure_valid()

        assert result.access_key == "AKID"

    @pytest.mark.asyncio
    async def test_ensure_valid_refreshes(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)

        mock_cognito = MagicMock()
        from botocore.credentials import Credentials
        mock_creds = Credentials("AKID", "SECRET", "TOKEN")
        auth._credentials = CradlewiseCredentials(cognito=mock_cognito, aws=mock_creds)

        new_creds = Credentials("AKID2", "SECRET2", "TOKEN2")
        with patch.object(auth, "_exchange_for_iam", return_value=new_creds):
            result = await auth.ensure_valid()

        assert result.access_key == "AKID2"

    @pytest.mark.asyncio
    async def test_ensure_valid_reauthenticates_on_error(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)

        mock_cognito = MagicMock()
        mock_cognito.check_token.side_effect = Exception("Token expired")
        from botocore.credentials import Credentials
        old_creds = Credentials("OLD", "OLD", "OLD")
        auth._credentials = CradlewiseCredentials(cognito=mock_cognito, aws=old_creds)

        new_cognito = MagicMock()
        new_creds = Credentials("NEW", "NEW", "NEW")
        with patch.object(auth, "_cognito_auth", return_value=new_cognito):
            with patch.object(auth, "_exchange_for_iam", return_value=new_creds):
                result = await auth.ensure_valid()

        assert result.access_key == "NEW"

    def test_cognito_auth_uses_config(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)

        with patch("pycradlewise.auth.Cognito") as MockCognito:
            mock_instance = MockCognito.return_value
            auth._cognito_auth()

            MockCognito.assert_called_once_with(
                app_config.cognito_user_pool_id,
                app_config.cognito_app_client_id,
                client_secret=app_config.cognito_app_client_secret,
                username="test@example.com",
            )
            mock_instance.authenticate.assert_called_once_with(password="password")

    def test_exchange_for_iam_uses_config(self, app_config):
        auth = CradlewiseAuth("test@example.com", "password", app_config)
        mock_cognito = MagicMock()
        mock_cognito.id_token = "test-id-token"

        mock_client = MagicMock()
        mock_client.get_id.return_value = {"IdentityId": "test-identity"}
        mock_client.get_credentials_for_identity.return_value = {
            "Credentials": {
                "AccessKeyId": "AK",
                "SecretKey": "SK",
                "SessionToken": "ST",
            }
        }

        with patch("pycradlewise.auth.boto3.client", return_value=mock_client):
            creds = auth._exchange_for_iam(mock_cognito)

        mock_client.get_id.assert_called_once_with(
            IdentityPoolId=app_config.cognito_identity_pool_id,
            Logins={
                f"cognito-idp.{app_config.cognito_region}.amazonaws.com/{app_config.cognito_user_pool_id}": "test-id-token"
            },
        )
        assert creds.access_key == "AK"
