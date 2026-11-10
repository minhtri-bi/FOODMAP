import { z } from 'zod';

export const statusSchema = z.enum(['want_to_try', 'tried', 'avoid']);
export const personalInputSchema = z.object({
  favorite: z.boolean(),
  status: statusSchema,
  personal_rating: z.number().min(0).max(5).nullable(),
  notes: z.string().max(4000),
  revision: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
});
export const restaurantInputSchema = z.object({
  name: z.string().trim().min(1).max(160),
  branch: z.string().trim().max(160),
  address: z.string().trim().min(1).max(500),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  branch_confirmed: z.literal(true),
  osm_id: z.string().regex(/^(node|way|relation)\/[1-9][0-9]*$/).optional(),
});
const restaurantSchema = restaurantInputSchema.omit({ branch_confirmed: true }).extend({
  id: z.string().uuid(),
  version: z.number().int().positive(),
  created_at: z.string(),
  source: z.object({
    id: z.string().uuid(), kind: z.literal('user_manual'), permission_basis: z.string(),
    observed_at: z.string(), storage_allowed: z.boolean(), cloud_eligible: z.boolean(),
    osm_origin: z.object({
      osm_id: z.string(), name: z.string(), address: z.string(), latitude: z.number(),
      longitude: z.number(), category: z.string(), source_url: z.string().url(),
      observed_at: z.string(), license: z.string(),
    }).nullable(),
  }),
  personal: personalInputSchema.extend({ updated_at: z.string() }),
});
const resultSchema = z.object({ data: restaurantSchema });
const pageSchema = z.object({
  data: z.array(restaurantSchema),
  meta: z.object({ total: z.number().int().nonnegative(), limit: z.number(), offset: z.number() }),
});
const errorSchema = z.object({ error: z.object({
  message: z.string(),
  details: z.array(z.object({ field: z.string(), message: z.string() })).optional(),
}) });

export type Restaurant = z.infer<typeof restaurantSchema>;
export type RestaurantInput = z.infer<typeof restaurantInputSchema>;
export type PersonalInput = z.infer<typeof personalInputSchema>;
export type PlaceStatus = z.infer<typeof statusSchema>;
export interface SearchFilters { q: string; status: string; favoriteOnly: boolean; offset: number }

async function request<T>(path: string, schema: z.ZodType<T>, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, headers: {
      ...(options?.body ? { 'Content-Type': 'application/json', 'X-FoodRoute-Request': '1' } : {}),
    } });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the local server. Check that the backend is running, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const parsed = errorSchema.safeParse(body);
    if (parsed.success) {
      const detail = parsed.data.error.details?.map(item => `${item.field}: ${item.message}`).join('; ');
      throw new Error(detail || parsed.data.error.message);
    }
    throw new Error(`The server returned HTTP ${response.status}. Retry without discarding your edits.`);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new Error('The server returned an invalid record. No data was accepted.');
  return parsed.data;
}

export function listRestaurants(filters: SearchFilters, signal: AbortSignal) {
  const query = new URLSearchParams({ q: filters.q, favorite_only: String(filters.favoriteOnly), offset: String(filters.offset) });
  if (filters.status) query.set('status', filters.status);
  return request(`/restaurants?${query}`, pageSchema, { signal });
}
export function getRestaurant(id: string, signal: AbortSignal) {
  return request(`/restaurants/${encodeURIComponent(id)}`, resultSchema, { signal });
}
export function createRestaurant(input: RestaurantInput) {
  return request('/restaurants', resultSchema, { method: 'POST', body: JSON.stringify(restaurantInputSchema.parse(input)) });
}
export function savePersonal(id: string, input: PersonalInput) {
  return request(`/restaurants/${encodeURIComponent(id)}/personal`, resultSchema, { method: 'PUT', body: JSON.stringify(personalInputSchema.parse(input)) });
}
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The operation failed. Your unsaved input is still here.';
}
export const statusLabels: Record<PlaceStatus, string> = {
  want_to_try: 'Want to try', tried: 'Tried', avoid: 'Avoid',
};
