import unittest
from unittest.mock import patch
import os

from backend.app.fixture_guard import is_fixture_mode_allowed, assert_database_available
from backend.app.exceptions import DatabaseUnavailableError


class TestFixtureGuard(unittest.TestCase):
    """Test suite ensuring Rule 5 & LEVEL 1.5 (No silent fake data) is strictly enforced."""

    def test_fixture_allowed_when_env_var_is_one(self):
        with patch.dict(os.environ, {"USE_FIXTURES": "1"}):
            self.assertTrue(is_fixture_mode_allowed())
            # Should not raise
            assert_database_available(Exception("DB down"), "test_op")

    def test_fixture_allowed_when_env_var_is_true(self):
        with patch.dict(os.environ, {"USE_FIXTURES": "true"}):
            self.assertTrue(is_fixture_mode_allowed())

    def test_fixture_denied_when_env_zero(self):
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            self.assertFalse(is_fixture_mode_allowed())
            with self.assertRaises(DatabaseUnavailableError) as ctx:
                assert_database_available(Exception("Connection refused"), "fetch_kpis")
            self.assertIn("Database unavailable", str(ctx.exception))
            self.assertIn("NO SILENT FAKE DATA", str(ctx.exception).upper())

    def test_fixture_denied_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_fixture_mode_allowed())
            with self.assertRaises(DatabaseUnavailableError):
                assert_database_available(Exception("Connection refused"), "fetch_kpis")


if __name__ == "__main__":
    unittest.main()
