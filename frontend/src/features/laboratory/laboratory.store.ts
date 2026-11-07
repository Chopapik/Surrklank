import { create } from 'zustand';
import type { LaboratoryMessage } from './laboratory.types';

interface LaboratoryStore {
  snapshot: LaboratoryMessage;
  receive: (snapshot: LaboratoryMessage) => void;
  disconnected: () => void;
}
export const useLaboratoryStore = create<LaboratoryStore>((set) => ({
  snapshot: { type: 'laboratory', available: false, supported: false, devices: [] },
  receive: (snapshot) => set({ snapshot }),
  disconnected: () => set(({ snapshot }) => ({ snapshot: {
    ...snapshot, available: false,
    devices: snapshot.devices.map((device) => ({ ...device, state: 'unknown', track0: null, position_estimate: null })),
  } })),
}));
