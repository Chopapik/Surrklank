import { z } from 'zod';
import { deviceInfoSchema } from '../connection/connection.types';

export type FirmwareTransport = 'usb' | 'ota';

export const serialPortsSchema = z.array(z.object({
  port: z.string(),
  name: z.string(),
}));
export type SerialPort = z.infer<typeof serialPortsSchema>[number];

const firmwareResultSchema = deviceInfoSchema.extend({
  transfer_seconds: z.number(),
  transfer_interval_us: z.number().nullable(),
  build_seconds: z.number(),
  total_seconds: z.number(),
  transport: z.enum(['usb', 'ble']),
});
export type FirmwareResult = z.infer<typeof firmwareResultSchema>;

const firmwareEventSchema = z.object({
  at: z.string(),
  job: z.string().nullable(),
  stage: z.string(),
  progress: z.number().optional(),
  error: z.string().optional(),
}).passthrough();
export type FirmwareEvent = z.infer<typeof firmwareEventSchema>;

export const firmwareSnapshotSchema = z.object({
  stage: z.string(),
  progress: z.number().nullable(),
  error: z.string().nullable(),
  result: firmwareResultSchema.nullable(),
  busy: z.boolean(),
  events: z.array(firmwareEventSchema),
});
export type FirmwareSnapshot = z.infer<typeof firmwareSnapshotSchema>;

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
