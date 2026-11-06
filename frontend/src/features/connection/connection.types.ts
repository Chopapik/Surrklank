export type ConnectionStatus =
  | 'unknown'
  | 'disconnected'
  | 'scanning'
  | 'connecting'
  | 'connected'
  | 'error';

export type DiscoveryStatus =
  | 'searching'
  | 'connecting'
  | 'not_found'
  | 'connected'
  | 'paused'
  | 'unavailable';

export type ConnectionAction = 'connect' | 'disconnect' | 'ping' | 'cancel';

export interface DeviceInfo {
  identity: string;
  version: string;
  slot: number;
  trial: boolean;
  ota: string;
  received: number;
  error: number;
  reset_reason: number;
  interval_us?: number;
  latency?: number;
}

export interface PingResult {
  ok: boolean;
  rtt_ms?: number | null;
  at?: string | null;
  reply?: string | null;
  error?: string | null;
}

export interface ConnectionEvent {
  at: string;
  state: string;
  error: string | null;
  session: number;
}

export interface ConnectionSnapshot {
  state: ConnectionStatus;
  connected: boolean;
  error: string | null;
  session: number;
  last_ping: PingResult | null;
  device: DeviceInfo | null;
  events: ConnectionEvent[];
  mtu: number | null;
  discovery: DiscoveryStatus;
}
