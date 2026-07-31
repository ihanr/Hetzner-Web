import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


SOURCE = Path(__file__).with_name("production-main.py")
spec = importlib.util.spec_from_file_location("production_main", SOURCE)
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


def api_error(status, code, message):
    response = requests.Response()
    response.status_code = status
    response.url = "https://api.hetzner.cloud/v1/servers"
    response._content = (
        f'{{"error":{{"code":"{code}","message":"{message}"}}}}'.encode()
    )
    return requests.HTTPError(response=response)


class FakeClient(main.HetznerClient):
    def __init__(self, create_results):
        super().__init__("unused")
        self.create_results = list(create_results)
        self.create_locations = []
        self.deleted = []

    def get_server(self, server_id):
        return {
            "id": server_id,
            "name": "4",
            "server_type": {"name": "cx33"},
            "location": {"name": "nbg1"},
        }

    def delete_server(self, server_id):
        self.deleted.append(server_id)
        return True

    def _request(self, method, endpoint, **kwargs):
        self.create_locations.append(kwargs["json"]["location"])
        result = self.create_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return {
            "server": {
                "id": result,
                "name": "4",
                "public_net": {"ipv4": {"ip": "192.0.2.44"}},
            }
        }


class LocationNormalizationTests(unittest.TestCase):
    def test_normalizes_configured_locations(self):
        config = {
            "rebuild": {
                "location_fallbacks": ["nbg1", "", "fsn1", "nbg1", "hel1"]
            }
        }
        self.assertEqual(
            main._rebuild_locations(config, "nbg1"),
            ["nbg1", "fsn1", "hel1"],
        )

    def test_missing_config_uses_old_location(self):
        self.assertEqual(main._rebuild_locations({}, "nbg1"), ["nbg1"])


class RebuildFallbackTests(unittest.TestCase):
    def config(self):
        return {
            "rebuild": {
                "snapshot_id_map": {"4": 412977893},
                "location_fallbacks": ["nbg1", "fsn1", "hel1"],
            }
        }

    def run_rebuild(self, results):
        client = FakeClient(results)
        with patch.object(main.time, "sleep"):
            result = client.rebuild_server(444, self.config())
        return client, result

    def test_first_location_success_stops_fallback(self):
        client, result = self.run_rebuild([9001])
        self.assertEqual(client.deleted, [444])
        self.assertEqual(client.create_locations, ["nbg1"])
        self.assertTrue(result["success"])
        self.assertEqual(result["new_location"], "nbg1")

    def test_412_falls_back_to_second_location(self):
        client, result = self.run_rebuild(
            [api_error(412, "resource_unavailable", "capacity"), 9002]
        )
        self.assertEqual(client.create_locations, ["nbg1", "fsn1"])
        self.assertTrue(result["success"])
        self.assertEqual(result["new_location"], "fsn1")

    def test_two_412_errors_fall_back_to_third_location(self):
        client, result = self.run_rebuild(
            [
                api_error(412, "resource_unavailable", "capacity"),
                api_error(412, "resource_unavailable", "capacity"),
                9003,
            ]
        )
        self.assertEqual(client.create_locations, ["nbg1", "fsn1", "hel1"])
        self.assertTrue(result["success"])
        self.assertEqual(result["new_location"], "hel1")

    def test_all_locations_unavailable_returns_one_failure(self):
        client, result = self.run_rebuild(
            [
                api_error(412, "resource_unavailable", "capacity"),
                api_error(412, "resource_unavailable", "capacity"),
                api_error(412, "resource_unavailable", "capacity"),
            ]
        )
        self.assertEqual(client.create_locations, ["nbg1", "fsn1", "hel1"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "resource_unavailable")
        self.assertEqual(
            result["attempted_locations"], ["nbg1", "fsn1", "hel1"]
        )
        self.assertIn("未自动重试", result["error"])

    def test_non_capacity_error_stops_immediately(self):
        client, result = self.run_rebuild(
            [api_error(403, "forbidden", "insufficient permissions"), 9004]
        )
        self.assertEqual(client.create_locations, ["nbg1"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "forbidden")
        self.assertIn("insufficient permissions", result["error"])


class RebuildNotificationTests(unittest.TestCase):
    def test_success_notification_contains_actual_location(self):
        config = {
            "telegram": {
                "enabled": True,
                "bot_token": "bot",
                "chat_id": "chat",
            },
            "cloudflare": {},
        }
        client = Mock()
        client.rebuild_server.return_value = {
            "success": True,
            "new_server_id": 9002,
            "new_ip": "192.0.2.44",
            "new_location": "fsn1",
            "attempted_locations": ["nbg1", "fsn1"],
        }
        with (
            patch.object(main, "_send_telegram_markdown", return_value=True) as send,
            patch.object(main, "_record_rebuild_event"),
            patch.object(main, "_save_yaml"),
        ):
            main._perform_rebuild(444, "4", config, "测试", client)
        messages = "\n".join(call.args[2] for call in send.call_args_list)
        self.assertIn("fsn1", messages)


if __name__ == "__main__":
    unittest.main()
