import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main


class SyncEndpointTests(unittest.TestCase):
    def test_sync_start_accepts_configured_password(self):
        payload = main.SyncStartRequest(password="secret")

        with patch.object(main, "load_env_file"):
            with patch.dict(main.os.environ, {"SYNC_START_PASSWORD": "secret"}, clear=True):
                with patch.object(main.sync_runner, "start", return_value={"running": True}) as start:
                    response = main.start_database_sync(payload)

        self.assertEqual(response, {"running": True})
        start.assert_called_once_with()

    def test_sync_start_rejects_invalid_password(self):
        payload = main.SyncStartRequest(password="wrong")

        with patch.object(main, "load_env_file"):
            with patch.dict(main.os.environ, {"SYNC_START_PASSWORD": "secret"}, clear=True):
                with patch.object(main.sync_runner, "start") as start:
                    with self.assertRaises(HTTPException) as context:
                        main.start_database_sync(payload)

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Invalid sync password")
        start.assert_not_called()

    def test_sync_start_rejects_missing_or_blank_configured_password(self):
        payload = main.SyncStartRequest(password="secret")

        for env in ({}, {"SYNC_START_PASSWORD": " "}):
            with self.subTest(env=env):
                with patch.object(main, "load_env_file"):
                    with patch.dict(main.os.environ, env, clear=True):
                        with patch.object(main.sync_runner, "start") as start:
                            with self.assertRaises(HTTPException) as context:
                                main.start_database_sync(payload)

                self.assertEqual(context.exception.status_code, 503)
                self.assertEqual(context.exception.detail, "SYNC_START_PASSWORD is not configured")
                start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
