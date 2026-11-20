import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useLaboratoryStore } from './laboratory.store';
import { playLaboratory, stopLaboratory } from './laboratory.api';
import type { LaboratoryDeviceRequest } from './laboratory.types';

export function useLaboratory() {
  const snapshot = useLaboratoryStore((state) => state.snapshot);
  // Settings are kept for all 12 drives; the rows follow the connected firmware.
  const count = snapshot.devices.length || 8;
  const [entries, setDevices] = useState(Array.from({ length: 12 }, (_, index) => ({
    device_type: 'fdd' as const, device: index + 1, frequency_hz: 220, duration_ms: 3000, selected: index === 0,
  })));
  const devices = entries.slice(0, count);
  const play = useMutation({ mutationFn: playLaboratory, retry: false });
  const stop = useMutation({ mutationFn: stopLaboratory, retry: false });
  function update(device: number, change: Partial<LaboratoryDeviceRequest> & { selected?: boolean }) {
    setDevices((current) => current.map((entry) => entry.device === device ? { ...entry, ...change } : entry));
  }
  function start() {
    play.reset(); stop.reset();
    play.mutate(devices.filter((d) => d.selected).map(({ device_type, device, frequency_hz, duration_ms }) => ({ device_type, device, frequency_hz, duration_ms })));
  }
  return { snapshot, devices, update, start, stop: stop.mutate, pending: play.isPending,
    stopping: stop.isPending, error: play.error?.message ?? stop.error?.message };
}
