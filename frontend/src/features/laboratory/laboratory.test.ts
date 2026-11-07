import { describe, expect, it } from 'vitest';
import { laboratoryMessageSchema } from './laboratory.types';
import { parseDeviceSocketMessage } from '../connection/deviceSocket.types';

function snapshot() {
  return { type: 'laboratory', supported: true, available: true, devices: Array.from({ length: 8 }, (_, index) => ({
    device_type: 'fdd', device: index + 1, sequence: 1, batch: 1, state: 'playing',
    frequency_hz: 220, duration_ms: 3000, elapsed_ms: 200, track0: false,
    left_track0: true, toward_zero: false, steps_issued: 40, return_steps: 0,
    position_estimate: 40, error_code: 0, message: null,
  })) };
}

describe('Laboratory WebSocket boundary', () => {
  it('accepts an independent typed snapshot on the existing socket', () => {
    expect(parseDeviceSocketMessage(JSON.stringify(snapshot()))?.type).toBe('laboratory');
  });

  it('rejects incomplete or duplicate device snapshots', () => {
    const incomplete = snapshot();
    incomplete.devices.pop();
    expect(laboratoryMessageSchema.safeParse(incomplete).success).toBe(false);
    const duplicate = snapshot();
    duplicate.devices[1].device = 1;
    expect(laboratoryMessageSchema.safeParse(duplicate).success).toBe(false);
  });

  it('rejects malformed telemetry before it enters Zustand', () => {
    const invalid = snapshot();
    invalid.devices[0].state = 'success';
    expect(parseDeviceSocketMessage(JSON.stringify(invalid))).toBeNull();
    expect(parseDeviceSocketMessage(JSON.stringify({ ...snapshot(), available: 'yes' }))).toBeNull();
  });
});
