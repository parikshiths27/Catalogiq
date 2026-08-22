/**
 * Resolves the base URL for API requests.
 * - In local development: defaults to empty string '' (using Vite dev proxy)
 * - In production (e.g. Vercel): uses VITE_API_URL if defined (e.g. 'https://catalogiq-backend.onrender.com')
 */
const RAW_API_URL: string = import.meta.env.VITE_API_URL || '';
export const API_BASE_URL: string = RAW_API_URL.replace(/\/+$/, '');

export function apiUrl(endpoint: string): string {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${API_BASE_URL}${cleanEndpoint}`;
}
