import unittest

from app.utils.helpers import get_server_location_name


class ServerLocationTests(unittest.TestCase):
    def test_reads_current_location_shape(self):
        server = {
            "location": {"id": 1, "name": "nbg1"},
            "datacenter": None,
        }

        self.assertEqual(get_server_location_name(server), "nbg1")

    def test_falls_back_to_legacy_datacenter_shape(self):
        server = {
            "datacenter": {
                "id": 2,
                "name": "nbg1-dc3",
                "location": {"id": 1, "name": "nbg1"},
            }
        }

        self.assertEqual(get_server_location_name(server), "nbg1")

    def test_rejects_response_without_location(self):
        with self.assertRaisesRegex(
            ValueError,
            "Hetzner server response does not contain a location name",
        ):
            get_server_location_name({"id": 123, "name": "missing-location"})


if __name__ == "__main__":
    unittest.main()
