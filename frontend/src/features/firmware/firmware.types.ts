import type { DeviceInfo } from '../connection/connection.types';

export type FirmwareTransport = 'usb' | 'ota';

export interface SerialPort {
  port: string;
  name: string;
}

export interface FirmwareResult extends DeviceInfo {
  transfer_seconds: number;
  transfer_interval_us: number | null;
  build_seconds: number;
  total_seconds: number;
  transport: 'usb' | 'ble';
}

export interface FirmwareEvent {
  at: string;
  job: string | null;
  stage: string;
  progress?: number;
  error?: string;
  [key: string]: unknown;
}

export interface FirmwareSnapshot {
  stage: string;
  progress: number | null;
  error: string | null;
  result: FirmwareResult | null;
  busy: boolean;
  events: FirmwareEvent[];
}

export const initialFirmware: FirmwareSnapshot = {
  stage: '—',
  progress: null,
  error: null,
  result: null,
  busy: false,
  events: [],
};

export const firmwareStatusKey = ['firmware', 'status'] as const;
export const firmwarePortsKey = ['firmware', 'ports'] as const;
