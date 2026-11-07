import { z } from 'zod';

export const connectionStatusSchema = z.enum([
  'unknown', 'disconnected', 'scanning', 'connecting', 'connected', 'error',
]);
export type ConnectionStatus = z.infer<typeof connectionStatusSchema>;

const discoveryStatusSchema = z.enum([
  'searching', 'connecting', 'not_found', 'connected', 'paused', 'unavailable',
]);
export type DiscoveryStatus = z.infer<typeof discoveryStatusSchema>;

export type ConnectionAction = 'connect' | 'disconnect' | 'ping';

export const deviceInfoSchema = z.object({
  identity: z.string(),
  version: z.string(),
  slot: z.number(),
  trial: z.boolean(),
  ota: z.string(),
  received: z.number(),
  error: z.number(),
  reset_reason: z.number(),
  interval_us: z.number().optional(),
  latency: z.number().optional(),
  atx_on: z.boolean().optional(),
}).passthrough();
export type DeviceInfo = z.infer<typeof deviceInfoSchema>;

const pingResultSchema = z.object({
  ok: z.boolean(),
  rtt_ms: z.number().nullable().optional(),
  at: z.string().nullable().optional(),
  reply: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
});
export type PingResult = z.infer<typeof pingResultSchema>;

const connectionEventSchema = z.object({
  at: z.string(),
  state: z.string(),
  error: z.string().nullable(),
  session: z.number(),
});
export type ConnectionEvent = z.infer<typeof connectionEventSchema>;

const deviceFirmwareSchema = z.object({
  stage: z.string(),
  received: z.number(),
  error: z.number(),
});

export const connectionSnapshotSchema = z.object({
  state: connectionStatusSchema,
  connected: z.boolean(),
  error: z.string().nullable(),
  session: z.number(),
  last_ping: pingResultSchema.nullable(),
  device: deviceInfoSchema.nullable(),
  events: z.array(connectionEventSchema),
  mtu: z.number().nullable(),
  discovery: discoveryStatusSchema,
  // Missing fields from older snapshots become explicit values in application state.
  atx_on: z.boolean().nullable().optional().default(null),
  subscribed: z.boolean().optional().default(false),
  operation: z.string().nullable().optional().default(null),
  device_firmware: deviceFirmwareSchema.nullable().optional().default(null),
});
export type ConnectionSnapshot = z.infer<typeof connectionSnapshotSchema>;
