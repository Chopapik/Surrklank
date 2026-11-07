import { useMutation } from '@tanstack/react-query';
import { useConnectionStore } from '../connection/connection.store';

export function useAtx() {
  const connection = useConnectionStore((state) => state.connection);
  const socketState = useConnectionStore((state) => state.socketState);
  const on = socketState === 'ready' && connection?.connected
    ? connection.atx_on ?? null : null;
  const mutation = useMutation({
    mutationFn: async (state: 'on' | 'off') => {
      const response = await fetch('/api/atx', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail ?? 'ATX request failed');
      }
    },
    retry: false,
  });

  // Only ESP32 snapshots update the switch; HTTP success is not a state source.
  return { on, setState: mutation.mutate, pending: mutation.isPending, error: mutation.error?.message };
}
