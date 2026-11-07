import { describe, expect, it } from 'vitest';
import { parseDeviceStateMessage } from './deviceSocket.types';

function message() {
  return {
    type: 'state',
    connection: {
      state: 'connected', connected: true, error: null, session: 1,
      last_ping: null, device: null, events: [], mtu: 498, discovery: 'connected',
    },
    firmware: {
      stage: 'idle', progress: null, error: null, result: null, busy: false, events: [],
    },
  };
}

describe('device state contract', () => {
  it('accepts older snapshots and normalizes optional state fields', () => {
    const parsed = parseDeviceStateMessage(JSON.stringify(message()));
    expect(parsed?.connection).toMatchObject({
      atx_on: null, operation: null, subscribed: false, device_firmware: null,
    });
    expect(parsed?.connection.connected).toBe(true);
  });

  it('accepts explicit null and ignores additional envelope fields', () => {
    const parsed = parseDeviceStateMessage(JSON.stringify({
      ...message(), extra: 'future field',
      connection: { ...message().connection, operation: null },
    }));
    expect(parsed?.connection.operation).toBeNull();
  });

  it('rejects malformed nested state instead of passing it to the store', () => {
    expect(parseDeviceStateMessage(JSON.stringify({
      ...message(), connection: { ...message().connection, connected: 'yes' },
    }))).toBeNull();
    expect(parseDeviceStateMessage(JSON.stringify({
      ...message(), firmware: { ...message().firmware, busy: 'false' },
    }))).toBeNull();
    expect(parseDeviceStateMessage(JSON.stringify({
      ...message(), connection: { ...message().connection, atx_on: 1 },
    }))).toBeNull();
  });

  it('ignores malformed JSON, unknown messages and unsupported connection states', () => {
    expect(parseDeviceStateMessage('{')).toBeNull();
    expect(parseDeviceStateMessage('null')).toBeNull();
    expect(parseDeviceStateMessage(JSON.stringify({ ...message(), type: 'other' }))).toBeNull();
    expect(parseDeviceStateMessage(JSON.stringify({
      ...message(), connection: { ...message().connection, state: 'unsupported' },
    }))).toBeNull();
  });
});
