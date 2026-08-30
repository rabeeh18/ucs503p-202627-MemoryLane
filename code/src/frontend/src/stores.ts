import { writable } from 'svelte/store';

export interface Webpage {
  id: string;
  url: string;
  title: string;
  domain?: string;
  timestamp: string;
}

export const searchQuery = writable<string>('');
export const results = writable<Webpage[]>([]);
export const isLoading = writable<boolean>(false);
export const searchPerformed = writable<boolean>(false);
export const error = writable<string | null>(null);
