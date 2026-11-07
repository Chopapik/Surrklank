import { z } from 'zod';

const errorResponseSchema = z.object({ detail: z.string() });

export async function readResponse(response: Response, fallbackMessage: string): Promise<unknown> {
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = errorResponseSchema.safeParse(data);
    throw new Error(error.success ? error.data.detail : fallbackMessage);
  }
  return data;
}
