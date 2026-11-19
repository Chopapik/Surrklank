import { useMutation } from '@tanstack/react-query';
import { setSelectLine } from './drives.api';
import { useConnectionStore } from '../connection/connection.store';

export function useDrives() {
  const connection = useConnectionStore((state) => state.connection);
  const socketState = useConnectionStore((state) => state.socketState);
  const lines = socketState === 'ready' && connection?.connected ? connection.select_lines : null;
  const mutation = useMutation({ mutationFn: setSelectLine, retry: false });
  return { lines, setLine: mutation.mutate, pending: mutation.isPending, error: mutation.error?.message };
}
