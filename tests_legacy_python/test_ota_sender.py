import asyncio
import binascii
import struct
from types import SimpleNamespace
import unittest
from legacy_python_backend.ota import OtaTransport, command_packet, sector_packets, crc, COMMAND, FIRMWARE


class OfficialProtocolTests(unittest.TestCase):
    def test_crc_is_standard_xmodem(self):
        self.assertEqual(crc(b"123456789"), 0x31C3)

    def test_start_command_layout_and_crc(self):
        packet = command_packet(1, 608640)
        self.assertEqual(len(packet), 20)
        self.assertEqual(struct.unpack_from("<HI", packet), (1, 608640))
        self.assertEqual(int.from_bytes(packet[18:], "little"), binascii.crc_hqx(packet[:18], 0))

    def test_sector_fragmentation_preserves_data_index_sequence_and_crc(self):
        for capacity in (20, 128, 244, 495):
            for size in (1, 239, 240, 241, 4095, 4096):
                with self.subTest(capacity=capacity, size=size):
                    block = bytes(i % 251 for i in range(size))
                    packets = list(sector_packets(42, block, capacity))
                    self.assertTrue(all(len(p) <= capacity for p in packets))
                    self.assertTrue(all(int.from_bytes(p[:2], "little") == 42 for p in packets))
                    self.assertEqual([p[2] for p in packets[:-1]], list(range(len(packets) - 1)))
                    self.assertEqual(packets[-1][2], 255)
                    self.assertEqual(
                        b"".join(p[3:] for p in packets[:-1]) + packets[-1][3:-2], block
                    )
                    self.assertEqual(int.from_bytes(packets[-1][-2:], "little"), crc(block))


class Client:
    is_connected = True
    mtu_size = 247

    def __init__(self, bad=False):
        self.services = self
        self.callbacks = {}
        self.codes = []
        self.buffer = bytearray()
        self.bad = bad

    def get_characteristic(self, uuid):
        return SimpleNamespace(max_write_without_response_size=244)

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def stop_notify(self, uuid):
        pass

    def ack(self, uuid, payload):
        packet = payload + bytes(18 - len(payload))
        packet += struct.pack("<H", crc(packet))
        if self.bad and uuid == FIRMWARE:
            packet = packet[:-1] + bytes([packet[-1] ^ 1])
        self.callbacks[uuid](None, packet)

    async def write_gatt_char(self, uuid, data, response):
        if uuid == COMMAND:
            code = int.from_bytes(data[:2], "little")
            self.codes.append(code)
            self.ack(uuid, struct.pack("<HHH", 3, code, 0) + b"\x03")
        else:
            sector, sequence = struct.unpack_from("<HB", data)
            if sequence == 255:
                self.buffer.extend(data[3:-2])
                self.ack(uuid, struct.pack("<HH", sector, 0))
            else:
                self.buffer.extend(data[3:])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_image_and_stop_receipt(self):
        image = bytes(i % 251 for i in range(12345))
        client = Client()
        self.assertTrue(await OtaTransport(client).transfer(image))
        self.assertEqual(bytes(client.buffer), image)
        self.assertEqual(client.codes, [1, 2])

    async def test_corrupt_receipt_aborts_without_replay(self):
        client = Client(bad=True)
        with self.assertRaisesRegex(RuntimeError, "CRC"):
            await OtaTransport(client).transfer(bytes(5000))
        self.assertEqual(client.codes, [1])


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_advertised_window_with_large_mtu_preserves_full_image(self):
        client = Client()
        client.mtu_size = 498
        client.get_characteristic = lambda _: SimpleNamespace(max_write_without_response_size=495)
        data = bytes(i % 251 for i in range(20000))
        sender = OtaTransport(client)
        await sender.transfer(data)
        self.assertEqual(client.buffer, data)
        self.assertEqual(sender.details["sector_window"], 3)
        self.assertEqual(sender.details["packet_bytes"], 495)


class IndexedReceiptClient(Client):
    mtu_size = 498

    def __init__(self):
        super().__init__()
        self.waiting = []
        self.remaining = 0
        self.last_ack = None

    def get_characteristic(self, uuid):
        return SimpleNamespace(max_write_without_response_size=495)

    async def write_gatt_char(self, uuid, data, response):
        if uuid == COMMAND and int.from_bytes(data[:2], "little") == 1:
            size = int.from_bytes(data[2:6], "little")
            self.remaining = (size + 4095) // 4096
        await super().write_gatt_char(uuid, data, response)

    def ack(self, uuid, payload):
        if uuid != FIRMWARE:
            return super().ack(uuid, payload)
        self.waiting.append(payload)
        count = min(3, self.remaining)
        if len(self.waiting) == count:
            if self.last_ack is not None:
                super().ack(uuid, self.last_ack)
            for frame in reversed(self.waiting):
                super().ack(uuid, frame)
            super().ack(uuid, self.waiting[0])
            self.last_ack = self.waiting[0]
            self.waiting.clear()
            self.remaining -= count


class IndexedReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_out_of_order_and_duplicate_receipts_do_not_replay_data(self):
        client = IndexedReceiptClient()
        data = bytes(i % 251 for i in range(22000))
        sender = OtaTransport(client)
        progress = []
        await sender.transfer(data, progress.append)
        self.assertEqual(bytes(client.buffer), data)
        self.assertEqual(client.codes, [1, 2])
        self.assertEqual(progress[-1], 100)
        self.assertEqual(len(progress), (len(data) + 4095) // 4096)
        self.assertGreater(sender.details["duplicate_receipts"], 0)
