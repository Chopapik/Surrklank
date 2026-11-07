import { z } from 'zod';

const errorResponseSchema = z.object({ message: z.string().optional(), detail: z.string().optional() });

export async function readResponse(response: Response, fallbackMessage: string): Promise<unknown> {
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = errorResponseSchema.safeParse(data);
    throw new Error(error.success ? error.data.message ?? error.data.detail ?? fallbackMessage : fallbackMessage);
  }
  return data;
}
