import json
import sys
import unittest
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

import xiaomi_thermo as xt
from miio.cloud import CloudDeviceInfo


def build_device(
    did: str,
    name: str,
    model: str,
    desc: str,
    room_id: str = "",
    online: bool = True,
) -> CloudDeviceInfo:
    payload = {
        "did": did,
        "token": "token-value",
        "name": name,
        "model": model,
        "localip": "192.168.1.50",
        "desc": desc,
        "ssid": "test-wifi",
        "parent_id": "",
        "mac": "AA:BB:CC:DD:EE:FF",
        "isOnline": online,
    }
    if room_id:
        payload["room_id"] = room_id
    return CloudDeviceInfo.from_micloud(payload, "de")


class FakeMiCloudRpcClient:
    def request_country(self, endpoint, country, params):
        _ = country
        _ = json.loads(params["data"])

        if endpoint == "/v2/homeroom/gethome":
            return json.dumps(
                {
                    "result": {
                        "homelist": [
                            {
                                "roomlist": [
                                    {"id": "11", "name": "Bedroom"},
                                    {"id": "12", "name": "Living Room"},
                                ]
                            }
                        ]
                    }
                }
            )
        if endpoint.startswith("/home/rpc/"):
            return json.dumps({"code": 0, "result": ["231", "456"]})
        if endpoint == "/miotspec/prop/get":
            return json.dumps({"code": 0, "result": []})
        return json.dumps({"result": {}})


class FakeCloudInterfaceRpc:
    def __init__(self, username, password):
        _ = username
        _ = password
        self._micloud = FakeMiCloudRpcClient()

    def get_devices(self, locale=None):
        _ = locale
        thermometer = build_device(
            did="did-thermo",
            name="Bedroom Sensor",
            model="lumi.sensor_ht",
            desc="Fallback Room",
            room_id="12",
        )
        plug = build_device(
            did="did-plug",
            name="Desk Plug",
            model="chuangmi.plug.v3",
            desc="Office",
        )
        return {thermometer.did: thermometer, plug.did: plug}


class FakeMiCloudMiotClient:
    def request_country(self, endpoint, country, params):
        _ = country
        payload = json.loads(params["data"])

        if endpoint.startswith("/home/rpc/"):
            return json.dumps({"code": -1, "message": "unsupported"})
        if endpoint == "/miotspec/prop/get":
            params_list = payload["params"]
            return json.dumps(
                {
                    "code": 0,
                    "result": [
                        {
                            "siid": params_list[0]["siid"],
                            "piid": params_list[0]["piid"],
                            "value": 22.4,
                        },
                        {
                            "siid": params_list[1]["siid"],
                            "piid": params_list[1]["piid"],
                            "value": 54,
                        },
                    ],
                }
            )
        return json.dumps({"result": {}})


class FakeCloudInterfaceMiot:
    def __init__(self, username, password):
        _ = username
        _ = password
        self._micloud = FakeMiCloudMiotClient()

    def get_devices(self, locale=None):
        _ = locale
        thermometer = build_device(
            did="did-thermo-miot",
            name="Kitchen Sensor",
            model="miaomiaoce.sensor_ht.t1",
            desc="Kitchen",
            room_id="",
            online=False,
        )
        return {thermometer.did: thermometer}


class XiaomiThermoServiceTests(unittest.TestCase):
    def setUp(self):
        self._original_cloud_interface = xt.CloudInterface

    def tearDown(self):
        xt.CloudInterface = self._original_cloud_interface

    def test_missing_credentials_raises_value_error(self):
        service = xt.XiaomiThermoService(username="", password="")
        with self.assertRaises(ValueError):
            service.get_house_readings()

    def test_reads_values_via_rpc_and_room_mapping(self):
        xt.CloudInterface = FakeCloudInterfaceRpc
        service = xt.XiaomiThermoService(username="user", password="pass", country="de")

        payload = service.get_house_readings()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["items"]), 1)

        item = payload["items"][0]
        self.assertEqual(item["name"], "Bedroom Sensor")
        self.assertEqual(item["room"], "Living Room")
        self.assertEqual(item["online"], True)
        self.assertAlmostEqual(item["temperature"], 23.1)
        self.assertAlmostEqual(item["humidity"], 45.6)

    def test_falls_back_to_miot_spec(self):
        xt.CloudInterface = FakeCloudInterfaceMiot
        service = xt.XiaomiThermoService(username="user", password="pass", country="de")

        payload = service.get_house_readings()
        self.assertEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertEqual(item["room"], "Kitchen")
        self.assertEqual(item["online"], False)
        self.assertAlmostEqual(item["temperature"], 22.4)
        self.assertAlmostEqual(item["humidity"], 54.0)


if __name__ == "__main__":
    unittest.main()
