import { useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { firmwareStatusKey } from '../firmware/firmware.types';
import { useConnectionStore } from './connection.store';
import type { ConnectionAction, ConnectionSnapshot } from './connection.types';
import type { DeviceStateMessage } from './deviceSocket.types';

// A single WebSocket carries both connection state and firmware progress.
export function useDeviceSocket() {
  const queryClient = useQueryClient();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: number | undefined;
    let initialStateTimer: number | undefined;
    let pendingConnection: ConnectionSnapshot | null = null;
    let waitingForState = true;

    function receiveConnection(connection: ConnectionSnapshot) {
      const store = useConnectionStore.getState();
      store.setSnapshot(connection);
      if (!waitingForState) {
        store.confirmSnapshot(connection);
        return;
      }

      const stateChanged = pendingConnection?.state !== connection.state;
      pendingConnection = connection;
      const settling = ['unknown', 'scanning', 'connecting'].includes(connection.state);
      if (settling && connection.discovery !== 'unavailable') {
        window.clearTimeout(initialStateTimer);
        initialStateTimer = undefined;
        return;
      }
      // Ignore short startup transitions; later connection loss is immediate.
      if (initialStateTimer !== undefined && !stateChanged) return;
      window.clearTimeout(initialStateTimer);
      initialStateTimer = window.setTimeout(() => {
        waitingForState = false;
        initialStateTimer = undefined;
        if (pendingConnection) useConnectionStore.getState().confirmSnapshot(pendingConnection);
      }, 300);
    }

    function openSocket() {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
      socketRef.current = socket;

      socket.onmessage = (event: MessageEvent<string>) => {
        if (disposed || socketRef.current !== socket) return;
        let message: DeviceStateMessage;
        try {
          message = JSON.parse(event.data) as DeviceStateMessage;
        } catch {
          return;
        }
        if (message?.type !== 'state' || !message.connection || !message.firmware) return;
        queryClient.setQueryData(firmwareStatusKey, message.firmware);
        receiveConnection(message.connection);
      };

      socket.onclose = () => {
        if (disposed || socketRef.current !== socket) return;
        socketRef.current = null;
        waitingForState = true;
        pendingConnection = null;
        window.clearTimeout(initialStateTimer);
        initialStateTimer = undefined;
        useConnectionStore.getState().socketClosed();
        reconnectTimer = window.setTimeout(openSocket, 1000);
      };
    }

    openSocket();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(initialStateTimer);
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close();
    };
  }, [queryClient]);

  return useCallback((action: ConnectionAction) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action }));
  }, []);
}
