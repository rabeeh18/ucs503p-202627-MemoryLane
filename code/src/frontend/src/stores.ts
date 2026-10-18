import { writable } from 'svelte/store';

export interface SavedPage {
  id: string;
  url: string;
  title: string;
  domain: string;
  timestamp: string;
}

export interface SearchResult extends SavedPage {
  rank: number;
  snippet: string | null;
}

/** Text in the search box (shared by Home and Results). */
export const searchQuery = writable<string>('');
export const results = writable<SearchResult[]>([]);
export const resultsLoading = writable<boolean>(false);
export const resultsError = writable<{ message: string; status: number } | null>(null);

export const recentPages = writable<SavedPage[] | null>(null);
export const recentError = writable<string | null>(null);

/** Bumped after data changes (e.g. delete all) so lists reload. */
export const libraryVersion = writable<number>(0);
