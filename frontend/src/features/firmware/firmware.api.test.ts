import { afterEach, describe, expect, it, vi } from 'vitest';
import { listFirmwarePorts, startFirmwareUpload } from './firmware.api';

function respond(data: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe('firmware HTTP contracts', () => {
  it('reads valid ports and rejects malformed port data', async () => {
    respond([{ port: '/dev/cu.usbserial-1', name: 'CP2102' }]);
    await expect(listFirmwarePorts()).resolves.toEqual([{ port: '/dev/cu.usbserial-1', name: 'CP2102' }]);
    respond([{ port: 42 }]);
    await expect(listFirmwarePorts()).rejects.toThrow('Invalid USB port list received');
  });

  it('preserves the busy reason and sends no automatic retry', async () => {
    const fetchMock = respond({ detail: 'Firmware update in progress', operation: 'firmware_update' }, 409);
    await expect(startFirmwareUpload('ota', '')).rejects.toThrow('Firmware update in progress');
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/firmware/ota', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ isolatedHardwareConfirmed: true, port: '' }),
    }));
  });

  it('rejects an invalid accepted-job body', async () => {
    respond({ busy: true }, 202);
    await expect(startFirmwareUpload('usb', '/dev/cu.usbserial-1')).rejects.toThrow('check the live status before retrying');
  });
});
