import { useConnectionStore } from './connection.store';
import type { ConnectionStatus } from './connection.types';

const statusLabels: Record<ConnectionStatus, string> = {
  unknown: 'Łączenie…',
  scanning: 'Łączenie…',
  connecting: 'Łączenie…',
  disconnected: 'Rozłączony',
  connected: 'Połączony',
  error: 'Błąd połączenia',
};

export function useConnection() {
  const connection = useConnectionStore((state) => state.connection);
  const socketState = useConnectionStore((state) => state.socketState);
  const statusReady = useConnectionStore((state) => state.statusReady);
  const lastKnownState = useConnectionStore((state) => state.lastKnownState);
  const ready = socketState === 'ready';
  const state = ready && statusReady ? connection?.state ?? 'unknown' : lastKnownState ?? 'unknown';
  const statusLabel = ready && state === 'unknown' && connection?.discovery === 'unavailable'
    ? 'Stan BLE nieznany'
    : statusLabels[state];
  const socketLabel = ready
    ? 'Połączenie z aplikacją aktywne'
    : socketState === 'offline'
      ? lastKnownState
        ? 'Brak połączenia z aplikacją — pokazano ostatnio znany stan'
        : 'Brak połączenia z aplikacją — stan urządzenia nieznany'
      : lastKnownState
        ? 'Ostatnio znany stan — weryfikacja…'
        : 'Łączenie z aplikacją…';

  return {
    connection,
    ready,
    connected: ready && connection?.connected === true,
    statusLabel,
    socketLabel,
  };
}
