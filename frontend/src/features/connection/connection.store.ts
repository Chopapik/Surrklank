import { create } from 'zustand';
import type { ConnectionSnapshot } from './connection.types';

export type LastKnownState = 'connected' | 'disconnected';
type SocketState = 'waiting' | 'ready' | 'offline';

interface ConnectionStore {
  connection: ConnectionSnapshot | null;
  socketState: SocketState;
  lastKnownState: LastKnownState | null;
  setSnapshot: (connection: ConnectionSnapshot) => void;
  confirmSnapshot: (connection: ConnectionSnapshot) => void;
  socketClosed: () => void;
}

const storageKey = 'ble.lastConnectionState';

function readLastKnownState(): LastKnownState | null {
  try {
    const saved = localStorage.getItem(storageKey);
    return saved === 'connected' || saved === 'disconnected' ? saved : null;
  } catch {
    return null;
  }
}

function saveLastKnownState(state: LastKnownState): void {
  try {
    localStorage.setItem(storageKey, state);
  } catch {
    // The connection still works when browser storage is disabled.
  }
}

export const useConnectionStore = create<ConnectionStore>((set, get) => ({
  connection: null,
  socketState: 'waiting',
  lastKnownState: readLastKnownState(),

  setSnapshot: (connection) => set({ connection }),

  confirmSnapshot: (connection) => {
    const state = connection.state;
    const lastKnownState = state === 'connected' || state === 'disconnected'
      ? state
      : get().lastKnownState;
    if (lastKnownState && lastKnownState !== get().lastKnownState) {
      saveLastKnownState(lastKnownState);
    }
    set({ connection, socketState: 'ready', lastKnownState });
  },

  socketClosed: () => set({ socketState: 'offline' }),
}));
