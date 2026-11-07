import { z } from 'zod';

export const laboratoryStateSchema = z.enum(['unknown', 'staged', 'homing', 'checking_out', 'checking_return', 'ready', 'playing', 'parking', 'parked', 'error', 'stopped']);
export const laboratoryMessageSchema = z.object({
  type: z.literal('laboratory'), available: z.boolean(), supported: z.boolean(),
  devices: z.array(z.object({
    device_type: z.literal('fdd'), device: z.number().int().min(1).max(8),
    sequence: z.number(), batch: z.number(), state: laboratoryStateSchema,
    frequency_hz: z.number(), duration_ms: z.number(), elapsed_ms: z.number(),
    track0: z.boolean().nullable(), left_track0: z.boolean(), toward_zero: z.boolean(),
    steps_issued: z.number(), return_steps: z.number(), position_estimate: z.number().nullable(),
    error_code: z.number(), message: z.string().nullable(),
  })).length(8).refine((devices) => new Set(devices.map((device) => device.device)).size === 8),
});
export type LaboratoryMessage = z.infer<typeof laboratoryMessageSchema>;
export interface LaboratoryDeviceRequest { device_type: 'fdd'; device: number; frequency_hz: number; duration_ms: number }
export const stateLabels: Record<z.infer<typeof laboratoryStateSchema>, string> = {
  unknown: 'Nieznany', staged: 'Przyjęty', homing: 'Szuka TRACK0', checking_out: 'Sprawdza wyjście',
  checking_return: 'Sprawdza powrót', ready: 'Gotowy', playing: 'Gra', parking: 'Parkuje', parked: 'Zaparkowany', error: 'Błąd', stopped: 'Zatrzymany',
};
export const isLaboratoryActive = (state: string) => !['unknown', 'parked', 'error', 'stopped'].includes(state);
