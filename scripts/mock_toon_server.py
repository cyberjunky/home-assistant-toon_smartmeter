#!/usr/bin/env python3
"""Mock Toon server for testing Z-Wave powerplug integration.

Run with: python scripts/mock_toon_server.py
Server will listen on http://localhost:8080

Test endpoints:
- GET  /hdrv_zwave?action=getDevices.json  → Returns device data
- POST /hdrv_zwave? with action=basicCommand&nodeID=X&state=0|1 → Toggle plug
- POST /hdrv_zwave? with action=GetBasic&nodeID=X → Refresh plug state
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Mock device data (based on your Toon2 with Z-Wave plugs example)
DEVICES = {
    "dev_settings_device": {
        "uuid": "bcbd7d66-2b06-426d-b414-adc7558bb666",
        "name": "settings_device",
        "internalAddress": "settings_device",
        "type": "settings_device",
    },
    "dev_4": {
        "uuid": "9f0a31af-41af-4208-beed-57519e47a304",
        "name": "Plug 1 Z-wave",
        "internalAddress": "4",
        "type": "FGWP011",
        "supportsCrc": "0",
        "ccList": "72 86 70 85 8e 25 73 32 31 7a ef 25 32 31",
        "supportedCC": "72 86 70 85 8e 25 73 32 31 7a ef 25 32 31",
        "nodeFlags": [],
        "IsConnected": "1",
        "HealthValue": "10",
        "DeviceName": "Plug 1 Z-wave",
        "TargetStatus": "1",
        "CurrentElectricityFlow": "0.30",
        "CurrentElectricityQuantity": "181130.00",
    },
    "dev_5": {
        "uuid": "83d0cd6d-ad15-45b0-ada8-27343cdcca84",
        "name": "Plug 2 Z-wave",
        "internalAddress": "5",
        "type": "FGWP011",
        "supportsCrc": "0",
        "ccList": "72 86 70 85 8e 25 73 32 31 7a ef 25 32 31",
        "supportedCC": "72 86 70 85 8e 25 73 32 31 7a ef 25 32 31",
        "nodeFlags": [],
        "IsConnected": "1",
        "HealthValue": "3",
        "DeviceName": "Plug 2 Z-wave",
        "TargetStatus": "1",
        "CurrentElectricityFlow": "0.40",
        "CurrentElectricityQuantity": "84770.00",
    },
    "dev_6": {
        "uuid": "7d5758c8-8e2b-4def-b9a9-c9f5c6f0cd28",
        "name": "Plug 3 Z-wave",
        "internalAddress": "6",
        "type": "FGWP011",
        "supportsCrc": "0",
        "ccList": "72 86 70 85 8e 25 73 32 31 7a ef 25 32 31",
        "supportedCC": "72 86 70 85 8e 25 73 32 31 7a ef 25 32 31",
        "nodeFlags": [],
        "IsConnected": "1",
        "HealthValue": "10",
        "DeviceName": "Plug 3 Z-wave",
        "TargetStatus": "1",
        "CurrentElectricityFlow": "0.70",
        "CurrentElectricityQuantity": "162010.00",
    },
    "dev_12": {
        "uuid": "ed67e292-c1d0-4fc1-b632-7d8465289ecf",
        "name": "HAE_METER_v2",
        "internalAddress": "12",
        "type": "HAE_METER_v2",
        "supportsCrc": "1",
        "ccList": "22 3c 3d 3e 56 60 70 72 7a 86 8b 73",
        "supportedCC": "22 3c 3d 3e 56 60 70 72 7a 86 8b 73",
        "nodeFlags": [],
        "IsConnected": "1",
        "HealthValue": "10",
        "DeviceName": "HAE_METER_v2",
        "CurrentSensorStatus": "UNKNOWN",
    },
    "dev_12.1": {
        "uuid": "bc9337e1-bfa4-4b6f-be3d-8099a6d64aeb",
        "name": "HAE_METER_v2_1",
        "internalAddress": "12.1",
        "type": "HAE_METER_v2_1",
        "supportsCrc": "0",
        "ccList": "3c 3d 3e 72 86",
        "supportedCC": "3c 3d 3e 72 86",
        "nodeFlags": [],
        "CurrentSensorStatus": "OPERATIONAL",
        "CurrentGasFlow": "7.00",
        "CurrentGasQuantity": "10664903.00",
        "DeviceName": "HAE_METER_v2_1",
    },
    "dev_12.3": {
        "uuid": "704a3c6b-0029-4ab4-9ade-91bcd3e60364",
        "name": "HAE_METER_v2_3",
        "internalAddress": "12.3",
        "type": "HAE_METER_v2_3",
        "supportsCrc": "0",
        "ccList": "3c 3d 3e 72 86",
        "supportedCC": "3c 3d 3e 72 86",
        "nodeFlags": [],
        "CurrentSensorStatus": "OPERATIONAL",
        "DeviceName": "HAE_METER_v2_3",
        "CurrentElectricityFlow": "244.00",
        "CurrentElectricityQuantity": "8519222.00",
    },
    "dev_12.5": {
        "uuid": "1a98a8f2-2bc4-418a-a4a5-812fa814d391",
        "name": "HAE_METER_v2_5",
        "internalAddress": "12.5",
        "type": "HAE_METER_v2_5",
        "supportsCrc": "0",
        "ccList": "3c 3d 3e 72 86",
        "supportedCC": "3c 3d 3e 72 86",
        "nodeFlags": [],
        "CurrentSensorStatus": "UNKNOWN",
        "DeviceName": "HAE_METER_v2_5",
        "CurrentElectricityFlow": "244.00",
        "CurrentElectricityQuantity": "37533807.00",
    },
}


class ToonHandler(BaseHTTPRequestHandler):
    """Handle requests to mock Toon server."""

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "text/javascript")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/hdrv_zwave":
            action = query.get("action", [""])[0]
            if action == "getDevices.json":
                print("GET getDevices.json")
                self._send_json(DEVICES)
                return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urlparse(self.path)

        if parsed.path == "/hdrv_zwave":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode()
            params = parse_qs(post_data)

            action = params.get("action", [""])[0]
            node_id = params.get("nodeID", [""])[0]

            if action == "basicCommand":
                state = params.get("state", [""])[0]
                # Find device by internalAddress and update TargetStatus
                for dev in DEVICES.values():
                    if dev.get("internalAddress") == node_id:
                        dev["TargetStatus"] = state
                        print(f"Set node {node_id} state to {state}")
                        break
                self._send_json({"result": "ok"})
                return

            if action == "GetBasic":
                print(f"GetBasic for node {node_id}")
                self._send_json({"result": "ok"})
                return

        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args) -> None:
        """Custom log format."""
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main() -> None:
    """Run the mock server."""
    host = "localhost"
    port = 8080
    server = HTTPServer((host, port), ToonHandler)
    print(f"Mock Toon server running at http://{host}:{port}")
    print(f"Configure integration with host: {host}, port: {port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
