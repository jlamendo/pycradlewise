"""Tests for pycradlewise.exceptions."""

from pycradlewise.exceptions import CradlewiseError, CradlewiseAuthError, CradlewiseApiError


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(CradlewiseAuthError, CradlewiseError)
        assert issubclass(CradlewiseApiError, CradlewiseError)
        assert issubclass(CradlewiseError, Exception)

    def test_auth_error(self):
        err = CradlewiseAuthError("bad creds")
        assert str(err) == "bad creds"
        assert isinstance(err, CradlewiseError)

    def test_api_error(self):
        err = CradlewiseApiError("timeout")
        assert str(err) == "timeout"
        assert isinstance(err, CradlewiseError)

    def test_base_error(self):
        err = CradlewiseError("generic")
        assert str(err) == "generic"
        assert isinstance(err, Exception)

    def test_can_be_caught_as_base(self):
        try:
            raise CradlewiseAuthError("test")
        except CradlewiseError as e:
            assert str(e) == "test"
