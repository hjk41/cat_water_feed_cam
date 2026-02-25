import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from miio.cloud import CloudDeviceInfo, CloudException, CloudInterface


DEFAULT_COUNTRY = "de"
DEFAULT_ROOM_NAME = "Unassigned"

THERMOMETER_MODEL_HINTS = (
    "sensor_ht",
    "weather",
    "hygro",
    "thermo",
    "temperature_humidity",
)

RPC_PROPERTY_QUERIES: Tuple[Tuple[str, str], ...] = (
    ("temperature", "humidity"),
    ("temp_dec", "humi_dec"),
    ("temp", "hum"),
)

MIOT_PROPERTY_CANDIDATES: Tuple[Tuple[Tuple[int, int], Tuple[int, int]], ...] = (
    ((2, 1), (2, 2)),
    ((3, 1), (3, 2)),
    ((3, 7), (3, 8)),
)


@dataclass
class ThermometerReading:
    did: str
    name: str
    room: str
    model: str
    temperature: Optional[float]
    humidity: Optional[float]
    online: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "did": self.did,
            "name": self.name,
            "room": self.room,
            "model": self.model,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "online": self.online,
        }


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None

    return None


def _normalize_temperature(value: Any) -> Optional[float]:
    numeric = _to_float(value)
    if numeric is None:
        return None

    absolute = abs(numeric)
    if absolute > 1000:
        numeric = numeric / 100.0
    elif absolute > 150:
        numeric = numeric / 10.0

    return round(numeric, 1)


def _normalize_humidity(value: Any) -> Optional[float]:
    numeric = _to_float(value)
    if numeric is None:
        return None

    absolute = abs(numeric)
    if absolute > 1000:
        numeric = numeric / 100.0
    elif absolute > 100:
        numeric = numeric / 10.0

    return round(numeric, 1)


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


class XiaomiThermoService:
    def __init__(
        self,
        username: str,
        password: str,
        country: str = DEFAULT_COUNTRY,
        model_hints: Optional[Iterable[str]] = None,
    ):
        self.username = username.strip()
        self.password = password.strip()
        self.country = (country or DEFAULT_COUNTRY).strip().lower() or DEFAULT_COUNTRY

        hints = {item.lower() for item in THERMOMETER_MODEL_HINTS}
        if model_hints:
            hints.update(item.strip().lower() for item in model_hints if item.strip())
        self.model_hints = tuple(sorted(hints))

    @classmethod
    def from_env(cls) -> "XiaomiThermoService":
        raw_hints = os.getenv("MIIO_SENSOR_MODELS", "")
        hint_list = [item.strip() for item in raw_hints.split(",") if item.strip()]
        return cls(
            username=os.getenv("MIIO_USERNAME", ""),
            password=os.getenv("MIIO_PASSWORD", ""),
            country=os.getenv("MIIO_COUNTRY", DEFAULT_COUNTRY),
            model_hints=hint_list,
        )

    def get_house_readings(self) -> Dict[str, Any]:
        if not self.username or not self.password:
            raise ValueError("MIIO_USERNAME and MIIO_PASSWORD are required.")

        cloud_interface = CloudInterface(username=self.username, password=self.password)

        try:
            devices = cloud_interface.get_devices(locale=self.country)
        except CloudException as exc:
            raise RuntimeError(f"Failed to fetch device list from Xiaomi cloud: {exc}") from exc

        micloud_client = getattr(cloud_interface, "_micloud", None)
        if micloud_client is None:
            raise RuntimeError("Could not initialize Xiaomi cloud client.")

        device_list = list(devices.values())
        room_lookup = self._build_room_lookup(micloud_client)

        readings: List[ThermometerReading] = []
        for device in device_list:
            if not self._is_thermometer(device):
                continue

            room_name = self._resolve_room(device, room_lookup)
            temperature, humidity = self._read_sensor_values(micloud_client, device)
            online = self._read_online_state(device)

            readings.append(
                ThermometerReading(
                    did=device.did,
                    name=device.name,
                    room=room_name,
                    model=device.model,
                    temperature=temperature,
                    humidity=humidity,
                    online=online,
                )
            )

        readings.sort(key=lambda item: (item.room.lower(), item.name.lower()))

        return {
            "count": len(readings),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": [item.to_dict() for item in readings],
        }

    def _is_thermometer(self, device: CloudDeviceInfo) -> bool:
        model = (device.model or "").lower()
        if any(hint in model for hint in self.model_hints):
            return True

        name = (device.name or "").lower()
        if "temperature" in name and "humidity" in name:
            return True

        raw = self._raw(device)
        raw_temp, raw_humidity = self._extract_raw_values(raw)
        return raw_temp is not None and raw_humidity is not None

    def _read_online_state(self, device: CloudDeviceInfo) -> bool:
        raw = self._raw(device)
        value = raw.get("isOnline", raw.get("online", True))
        if isinstance(value, str):
            lowered = value.strip().lower()
            return lowered in {"1", "true", "online", "yes"}
        return bool(value)

    def _resolve_room(self, device: CloudDeviceInfo, room_lookup: Dict[str, str]) -> str:
        raw = self._raw(device)
        room_name = _first_non_empty(
            raw.get("room_name"),
            raw.get("roomName"),
            raw.get("roomname"),
        )

        if room_name:
            return room_name

        room_id = raw.get("room_id", raw.get("roomid"))
        if room_id is not None:
            mapped = room_lookup.get(str(room_id))
            if mapped:
                return mapped

        return _first_non_empty(device.description, DEFAULT_ROOM_NAME) or DEFAULT_ROOM_NAME

    def _build_room_lookup(self, micloud_client: Any) -> Dict[str, str]:
        payload = {
            "fg": True,
            "fetch_share": True,
            "fetch_share_dev": True,
            "limit": 300,
        }

        for endpoint in ("/v2/homeroom/gethome", "/home/gethome"):
            response = self._request_json(
                micloud_client=micloud_client, endpoint=endpoint, payload=payload
            )
            if response is None:
                continue

            parsed = self._extract_rooms_from_response(response)
            if parsed:
                return parsed

        return {}

    def _extract_rooms_from_response(self, response: Dict[str, Any]) -> Dict[str, str]:
        result = response.get("result")
        if not isinstance(result, dict):
            return {}

        room_lookup: Dict[str, str] = {}

        home_candidates = []
        for key in ("homelist", "home_list", "homes", "list"):
            value = result.get(key)
            if isinstance(value, list):
                home_candidates.extend(value)

        for home in home_candidates:
            if not isinstance(home, dict):
                continue
            room_lists = (
                home.get("roomlist"),
                home.get("room_list"),
                home.get("rooms"),
            )
            for room_list in room_lists:
                if not isinstance(room_list, list):
                    continue
                for room in room_list:
                    if not isinstance(room, dict):
                        continue
                    room_id = room.get("id", room.get("room_id"))
                    room_name = _first_non_empty(
                        room.get("name"),
                        room.get("room_name"),
                        room.get("roomName"),
                    )
                    if room_id is None or not room_name:
                        continue
                    room_lookup[str(room_id)] = room_name

        return room_lookup

    def _read_sensor_values(
        self, micloud_client: Any, device: CloudDeviceInfo
    ) -> Tuple[Optional[float], Optional[float]]:
        raw = self._raw(device)
        raw_temp, raw_humidity = self._extract_raw_values(raw)
        temperature = _normalize_temperature(raw_temp)
        humidity = _normalize_humidity(raw_humidity)

        rpc_temp, rpc_humidity = self._read_values_with_rpc(micloud_client, device.did)
        if temperature is None:
            temperature = rpc_temp
        if humidity is None:
            humidity = rpc_humidity

        if temperature is not None and humidity is not None:
            return temperature, humidity

        miot_temp, miot_humidity = self._read_values_with_miot_spec(
            micloud_client, device.did
        )
        if temperature is None:
            temperature = miot_temp
        if humidity is None:
            humidity = miot_humidity

        return temperature, humidity

    def _read_values_with_rpc(
        self, micloud_client: Any, did: str
    ) -> Tuple[Optional[float], Optional[float]]:
        endpoint = f"/home/rpc/{did}"
        for temp_key, hum_key in RPC_PROPERTY_QUERIES:
            payload = {
                "id": 1,
                "method": "get_prop",
                "params": [temp_key, hum_key],
            }
            response = self._request_json(
                micloud_client=micloud_client, endpoint=endpoint, payload=payload
            )
            if response is None:
                continue

            result = response.get("result")
            if isinstance(result, list):
                temp = _normalize_temperature(result[0] if len(result) > 0 else None)
                humidity = _normalize_humidity(result[1] if len(result) > 1 else None)
                if temp is not None or humidity is not None:
                    return temp, humidity

            if isinstance(result, dict):
                temp, humidity = self._extract_raw_values(result)
                normalized_temp = _normalize_temperature(temp)
                normalized_humidity = _normalize_humidity(humidity)
                if normalized_temp is not None or normalized_humidity is not None:
                    return normalized_temp, normalized_humidity

        return None, None

    def _read_values_with_miot_spec(
        self, micloud_client: Any, did: str
    ) -> Tuple[Optional[float], Optional[float]]:
        endpoint = "/miotspec/prop/get"
        for (t_siid, t_piid), (h_siid, h_piid) in MIOT_PROPERTY_CANDIDATES:
            payload = {
                "params": [
                    {"did": did, "siid": t_siid, "piid": t_piid},
                    {"did": did, "siid": h_siid, "piid": h_piid},
                ]
            }
            response = self._request_json(
                micloud_client=micloud_client, endpoint=endpoint, payload=payload
            )
            if response is None:
                continue

            result = response.get("result")
            if not isinstance(result, list):
                continue

            value_map: Dict[Tuple[int, int], Any] = {}
            for item in result:
                if not isinstance(item, dict):
                    continue
                siid = item.get("siid")
                piid = item.get("piid")
                if siid is None or piid is None:
                    continue
                value_map[(int(siid), int(piid))] = item.get("value")

            temp = _normalize_temperature(value_map.get((t_siid, t_piid)))
            humidity = _normalize_humidity(value_map.get((h_siid, h_piid)))
            if temp is not None or humidity is not None:
                return temp, humidity

        return None, None

    def _request_json(
        self, micloud_client: Any, endpoint: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        params = {"data": json.dumps(payload, separators=(",", ":"))}
        try:
            response = micloud_client.request_country(endpoint, self.country, params)
        except Exception:
            return None

        if response is None:
            return None

        if isinstance(response, dict):
            return response

        if not isinstance(response, str):
            return None

        stripped = response.strip()
        if not stripped:
            return None

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, dict):
            return parsed
        return None

    def _extract_raw_values(self, payload: Dict[str, Any]) -> Tuple[Any, Any]:
        temp_keys = (
            "temperature",
            "temp",
            "temp_dec",
            "current_temperature",
            "temperature_value",
        )
        humidity_keys = (
            "humidity",
            "hum",
            "humi_dec",
            "relative_humidity",
            "humidity_value",
        )

        temperature = self._extract_first_key(payload, temp_keys)
        humidity = self._extract_first_key(payload, humidity_keys)
        return temperature, humidity

    def _extract_first_key(self, payload: Dict[str, Any], keys: Iterable[str]) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]

        nested = payload.get("prop")
        if isinstance(nested, dict):
            for key in keys:
                if key in nested:
                    return nested[key]

        extra = payload.get("extra")
        if isinstance(extra, str):
            try:
                extra_dict = json.loads(extra)
            except json.JSONDecodeError:
                extra_dict = None
            if isinstance(extra_dict, dict):
                for key in keys:
                    if key in extra_dict:
                        return extra_dict[key]

        return None

    def _raw(self, device: CloudDeviceInfo) -> Dict[str, Any]:
        if isinstance(device.raw_data, dict):
            return device.raw_data
        return {}
