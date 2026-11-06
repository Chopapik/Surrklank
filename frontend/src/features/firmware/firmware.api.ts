import type { FirmwareSnapshot, FirmwareTransport, SerialPort } from './firmware.types';

async function readResponse<T>(response: Response): Promise<T> {
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
    throw new Error(typeof detail === 'string' ? detail : 'Upload failed');
  }
  return data as T;
}

export async function listFirmwarePorts(): Promise<SerialPort[]> {
  return readResponse<SerialPort[]>(await fetch('/api/firmware/ports'));
}

export async function startFirmwareUpload(
  transport: FirmwareTransport,
  port: string,
): Promise<FirmwareSnapshot> {
  const response = await fetch(`/api/firmware/${transport}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ isolatedHardwareConfirmed: true, port }),
  });
  return readResponse<FirmwareSnapshot>(response);
}
