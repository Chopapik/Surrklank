import { readResponse } from '../../shared/http/readResponse';
import {
  firmwareSnapshotSchema,
  serialPortsSchema,
  type FirmwareSnapshot,
  type FirmwareTransport,
  type SerialPort,
} from './firmware.types';

export async function listFirmwarePorts(): Promise<SerialPort[]> {
  const response = await fetch('/api/firmware/ports');
  const ports = serialPortsSchema.safeParse(await readResponse(response, 'Could not list USB ports'));
  if (!ports.success) throw new Error('Invalid USB port list received');
  return ports.data;
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
  const firmware = firmwareSnapshotSchema.safeParse(await readResponse(response, 'Upload failed'));
  if (!firmware.success) {
    throw new Error('Invalid firmware response; check the live status before retrying');
  }
  return firmware.data;
}
