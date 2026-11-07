// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { useConnectionStore } from './features/connection/connection.store';
import type { ConnectionSnapshot } from './features/connection/connection.types';
import type { FirmwareSnapshot } from './features/firmware/firmware.types';

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = FakeWebSocket.OPEN;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  receive(connection: ConnectionSnapshot, firmware: FirmwareSnapshot = idleFirmware) {
    this.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({ type: 'state', connection, firmware }),
    }));
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}

const connected: ConnectionSnapshot = {
  state: 'connected', connected: true, error: null, session: 1,
  last_ping: null, device: null, events: [], mtu: 498, discovery: 'connected',
};
const idleFirmware: FirmwareSnapshot = {
  stage: 'idle', progress: null, error: null, result: null, busy: false, events: [],
};

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) throw new Error('WebSocket was not opened');
  return { ...view, socket };
}

async function establishConnection(socket: FakeWebSocket) {
  act(() => socket.receive(connected));
  await waitFor(() => expect((screen.getByRole('button', { name: 'Ping' }) as HTMLButtonElement).disabled).toBe(false));
}

describe('Surrklank interface', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    localStorage.clear();
    useConnectionStore.setState({ connection: null, socketState: 'waiting', lastKnownState: null });
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the last confirmed status during startup and sends ping only when clicked', async () => {
    useConnectionStore.setState({ lastKnownState: 'connected' });
    const { socket } = renderApp();
    expect(screen.getByRole('heading', { name: 'Surrklank' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Połączony' })).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Ping' }) as HTMLButtonElement).disabled).toBe(true);

    act(() => socket.receive({ ...connected, state: 'scanning', connected: false, discovery: 'searching' }));
    expect(screen.getByRole('heading', { name: 'Połączony' })).toBeTruthy();
    await establishConnection(socket);
    expect(socket.send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Ping' }));
    expect(socket.send).toHaveBeenCalledExactlyOnceWith(JSON.stringify({ action: 'ping' }));
  });

  it('shows firmware progress from WebSocket and disables conflicting actions', async () => {
    const { socket } = renderApp();
    await establishConnection(socket);
    act(() => socket.receive(connected, { ...idleFirmware, stage: 'ble_upload', busy: true, progress: 50 }));
    expect(screen.getByText('ble_upload')).toBeTruthy();
    expect((screen.getByRole('progressbar') as HTMLProgressElement).value).toBe(50);
    expect((screen.getByRole('button', { name: 'Ping' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Anuluj' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }));
    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ action: 'cancel' }));
  });

  it('uses the selected CP2102 port and asks for confirmation before USB upload', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([
      { port: '/dev/cu.usbserial-1', name: 'CP2102' },
      { port: '/dev/cu.usbserial-2', name: 'CP2102' },
    ]), { status: 200 }));
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(idleFirmware), { status: 202 }));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { socket } = renderApp();
    await establishConnection(socket);
    await screen.findByRole('option', { name: '/dev/cu.usbserial-2' });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '/dev/cu.usbserial-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kompiluj i wgraj przez USB' }));
    expect(confirm).toHaveBeenCalledOnce();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/firmware/usb');
    expect(JSON.parse(options.body as string)).toEqual({
      isolatedHardwareConfirmed: true, port: '/dev/cu.usbserial-2',
    });
  });

  it('does not send an OTA request when isolation confirmation is cancelled', async () => {
    const fetchMock = vi.mocked(fetch);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { socket } = renderApp();
    await establishConnection(socket);
    fireEvent.click(screen.getByRole('button', { name: 'Kompiluj i wgraj przez BLE OTA' }));
    expect(fetchMock).toHaveBeenCalledTimes(1); // Port list only.
  });

  it('shows an upload error without retrying the firmware request', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Device is busy' }), { status: 400 }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { socket } = renderApp();
    await establishConnection(socket);
    fireEvent.click(screen.getByRole('button', { name: 'Kompiluj i wgraj przez BLE OTA' }));
    await screen.findByText('Device is busy');
    await new Promise((resolve) => setTimeout(resolve, 1100));
    expect(fetchMock).toHaveBeenCalledTimes(2); // Port list and one OTA request.
  });

  it('keeps the last confirmed state and disables device commands when WebSocket closes', async () => {
    const { socket } = renderApp();
    await establishConnection(socket);
    act(() => socket.close());
    expect(screen.getByRole('heading', { name: 'Połączony' })).toBeTruthy();
    expect(screen.getByText(/pokazano ostatnio znany stan/)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Ping' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('reconnects the WebSocket and ignores messages from the closed socket', async () => {
    const { socket } = renderApp();
    await establishConnection(socket);
    act(() => socket.close());

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2), { timeout: 2500 });
    const newSocket = FakeWebSocket.instances[1];
    act(() => socket.receive({ ...connected, state: 'disconnected', connected: false }));
    expect(screen.getByRole('heading', { name: 'Połączony' })).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Ping' }) as HTMLButtonElement).disabled).toBe(true);

    await establishConnection(newSocket);
    expect(newSocket.send).not.toHaveBeenCalled();
  });
});
