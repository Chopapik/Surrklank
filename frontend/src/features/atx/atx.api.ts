import { readResponse } from '../../shared/http/readResponse';

export type AtxState = 'on' | 'off';

export async function setAtxState(state: AtxState): Promise<void> {
  const response = await fetch('/api/atx', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state }),
  });
  // The accepted response is not used to update state; ESP32 snapshots own it.
  await readResponse(response, 'ATX request failed');
}
