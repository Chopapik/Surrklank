import unittest
from unittest.mock import AsyncMock
from legacy_python_backend.device_service import DeviceService
from test_connection import connection


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_implicit_physical_maintenance(self):
        service = DeviceService(connection())
        for request in ({}, [], {"isolatedHardwareConfirmed": False}):
            with self.assertRaises(ValueError):
                await service.start("usb", request)
        self.assertIsNone(service.task)

    async def test_wrong_identity_is_never_confirmed(self):
        c = connection()
        c.info = AsyncMock(return_value={"identity": "wrong", "trial": True})
        c.command = AsyncMock()
        c._ping = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "identity"):
            await DeviceService(c).verify("expected")
        c.command.assert_not_awaited()
        c._ping.assert_not_awaited()

    async def test_trial_requires_identity_and_ping_before_confirmation(self):
        c = connection()
        c.info = AsyncMock(
            side_effect=[{"identity": "same", "trial": True}, {"identity": "same", "trial": False}]
        )
        order = []

        async def ping():
            order.append("ping")

        async def command(text):
            order.append(text)
            return "VALID"

        c._ping = ping
        c.command = command
        result = await DeviceService(c).verify("same")
        self.assertEqual(order, ["ping", "CONFIRM"])
        self.assertFalse(result["trial"])
