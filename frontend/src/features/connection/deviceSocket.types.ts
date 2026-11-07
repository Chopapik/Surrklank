import { z } from 'zod';
import { firmwareSnapshotSchema } from '../firmware/firmware.types';
import { connectionSnapshotSchema } from './connection.types';

export const deviceStateMessageSchema = z.object({
  type: z.literal('state'),
  connection: connectionSnapshotSchema,
  firmware: firmwareSnapshotSchema,
});
export type DeviceStateMessage = z.infer<typeof deviceStateMessageSchema>;

export function parseDeviceStateMessage(data: string): DeviceStateMessage | null {
  try {
    const parsed = deviceStateMessageSchema.safeParse(JSON.parse(data));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
