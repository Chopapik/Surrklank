import unittest
from fastapi.testclient import TestClient
from legacy_python_backend.main import create_app
from test_connection import connection


class WebSocketTests(unittest.TestCase):
    def test_state_and_manual_ping_are_pushed_without_rest_polling(self):
        app = create_app(connection())
        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 200)
            with client.websocket_connect("/ws") as ws:
                self.assertEqual(ws.receive_json()["connection"]["state"], "disconnected")
                ws.send_json({"action": "connect"})
                while (state := ws.receive_json())["connection"]["state"] != "connected":
                    pass
                self.assertIsNone(state["connection"]["last_ping"])
                ws.send_json({"action": "ping"})
                while not (state := ws.receive_json())["connection"]["last_ping"]:
                    pass
                self.assertTrue(state["connection"]["last_ping"]["ok"])
                self.assertEqual(len(app.state.connection.client.writes), 1)

    def test_upload_rejects_missing_isolation_and_foreign_origin(self):
        with TestClient(create_app(connection())) as client:
            self.assertEqual(client.post("/api/firmware/usb", json={}).status_code, 400)
            self.assertEqual(
                client.post(
                    "/api/firmware/ota",
                    json={"isolatedHardwareConfirmed": True},
                    headers={"Origin": "https://other.example"},
                ).status_code,
                403,
            )
            self.assertFalse(client.get("/api/connection").json()["firmware"]["busy"])

    def test_loss_is_pushed_without_another_command_or_ping(self):
        app = create_app(connection())
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"action": "connect"})
                while ws.receive_json()["connection"]["state"] != "connected":
                    pass
                native = app.state.connection.client
                native.is_connected = False
                # No callback, HTTP request or WebSocket command wakes the app.
                state = ws.receive_json()
                self.assertEqual(state["connection"]["state"], "disconnected")
                self.assertFalse(state["connection"]["connected"])
                self.assertEqual(native.writes, [])

    def test_disconnect_callback_from_native_thread_wakes_socket(self):
        app = create_app(connection())
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"action": "connect"})
                while ws.receive_json()["connection"]["state"] != "connected":
                    pass
                native = app.state.connection.client
                native.is_connected = False
                native.callback(native)
                state = ws.receive_json()
                self.assertEqual(state["connection"]["state"], "disconnected")
                self.assertEqual(native.writes, [])
