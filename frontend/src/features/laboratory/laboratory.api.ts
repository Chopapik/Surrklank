import { readResponse } from '../../shared/http/readResponse';
import type { LaboratoryDeviceRequest } from './laboratory.types';

export async function playLaboratory(devices: LaboratoryDeviceRequest[]): Promise<void> {
  await readResponse(await fetch('/api/laboratory/play', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ devices }),
  }), 'Nie potwierdzono uruchomienia paczki. Sprawdź aktualny stan przed ponowieniem.');
}
export async function stopLaboratory(device?: number): Promise<void> {
  await readResponse(await fetch(device === undefined ? '/api/laboratory/stop/all' : '/api/laboratory/stop', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    ...(device === undefined ? {} : { body: JSON.stringify({ device_type: 'fdd', device }) }),
  }), 'Nie potwierdzono zatrzymania. Sprawdź stan urządzeń.');
}
