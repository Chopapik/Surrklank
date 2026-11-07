import { useMutation } from '@tanstack/react-query';
import { setAtxState } from './atx.api';
import { useConnectionStore } from '../connection/connection.store';

export function useAtx() {
  const connection = useConnectionStore((state) => state.connection);
  const socketState = useConnectionStore((state) => state.socketState);
  const on = socketState === 'ready' && connection?.connected
    ? connection.atx_on ?? null : null;
  const mutation = useMutation({
    mutationFn: setAtxState,
    retry: false,
  });

  // Only ESP32 snapshots update the switch; HTTP success is not a state source.
  return { on, setState: mutation.mutate, pending: mutation.isPending, error: mutation.error?.message };
}
