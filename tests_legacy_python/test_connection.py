import asyncio
import json
from types import SimpleNamespace
import unittest
from legacy_python_backend.connection import BleConnection, COMMAND, INFO


class Scanner:
    @staticmethod
    async def find_device_by_filter(predicate, timeout):
        return SimpleNamespace(name="EM-MIDI-IDF")


class Client:
    def __init__(self, device, disconnected_callback, timeout):
        self.callback = disconnected_callback
        self.is_connected = False
        self.writes = []
        self.reply = b"IDLE"

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.callback(self)

    async def write_gatt_char(self, uuid, data, response):
        self.writes.append(bytes(data))
        self.reply = bytes(data).replace(b"PING ", b"PONG ")

    async def read_gatt_char(self, uuid):
        return (
            json.dumps({"identity": "a" * 64, "trial": False}).encode()
            if uuid == INFO
            else self.reply
        )


def connection():
    return BleConnection(scanner=Scanner, client_factory=Client)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_does_not_send_ping_or_create_heartbeat(self):
        c = connection()
        await c.connect()
        await asyncio.sleep(0.02)
        self.assertEqual(c.client.writes, [])
        self.assertIsNone(c.last_ping)
        await c.ping()
        self.assertTrue(c.last_ping["ok"])
        self.assertEqual(len(c.client.writes), 1)
        await c.disconnect()
        self.assertEqual(c.state, "disconnected")

    async def test_stale_disconnect_cannot_clear_new_session(self):
        c = connection()
        await c.connect()
        old = c.client
        await c.disconnect()
        await c.connect()
        old.callback(old)
        self.assertTrue(c.client.is_connected)
        self.assertEqual(c.state, "connected")
        await c.disconnect()

    async def test_real_disconnect_updates_state_without_ping(self):
        c = connection()
        await c.connect()
        client = c.client
        client.is_connected = False
        client.callback(client)
        self.assertEqual(c.state, "disconnected")
        self.assertIsNone(c.client)

    async def test_native_flag_loss_is_published_without_ping_or_callback(self):
        c = connection()
        await c.connect()
        client = c.client
        published = asyncio.Event()
        c.publish = published.set
        observer = asyncio.create_task(c.watch_link_state())
        try:
            client.is_connected = False
            await asyncio.wait_for(published.wait(), 1)
            self.assertEqual(c.state, "disconnected")
            self.assertIsNone(c.client)
            self.assertEqual(client.writes, [])
        finally:
            observer.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await observer

    async def test_disconnect_during_information_read_cannot_restore_connected(self):
        class LostDuringRead(Client):
            async def read_gatt_char(self, uuid):
                value = await super().read_gatt_char(uuid)
                self.is_connected = False
                self.callback(self)
                return value

        c = BleConnection(scanner=Scanner, client_factory=LostDuringRead)
        with self.assertRaisesRegex(ConnectionError, "disconnected"):
            await c.connect()
        self.assertNotEqual(c.state, "connected")
        self.assertFalse(c.snapshot()["connected"])
