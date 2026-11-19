import { readResponse } from '../../shared/http/readResponse';

export type SelectLine = 'DS0' | 'DS1' | 'DS2';
export const selectLines: SelectLine[] = ['DS0', 'DS1', 'DS2'];

export async function setSelectLine(request: { device: number; line: SelectLine }): Promise<void> {
  // ESP32 stores the line; the next INFO snapshot updates the view.
  await readResponse(await fetch('/api/drives/select', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
  }), 'Nie zmieniono linii SELECT.');
}
