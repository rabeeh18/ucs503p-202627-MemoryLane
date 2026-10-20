import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { createDeleteQueue, DELETE_DELAY_MS, ERROR_TOAST_MS } from './deletes.js';

describe('delayed delete with undo', () => {
  let remove;
  let queue;

  beforeEach(() => {
    vi.useFakeTimers();
    remove = vi.fn().mockResolvedValue(null);
    queue = createDeleteQueue({ remove });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('hides the page at once and shows an undo toast', () => {
    queue.schedule('p1');
    expect(get(queue.hidden).has('p1')).toBe(true);
    expect(get(queue.toasts)).toEqual([{ id: 1, kind: 'undo', message: 'Page deleted', pageId: 'p1' }]);
    expect(remove).not.toHaveBeenCalled();
  });

  it('sends the delete only when the toast expires', async () => {
    queue.schedule('p1');
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS - 1);
    expect(remove).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(remove).toHaveBeenCalledWith('p1', undefined);
    expect(get(queue.toasts)).toEqual([]);
    expect(get(queue.hidden).has('p1')).toBe(true); // stays gone
  });

  it('undo cancels the request and restores the page', async () => {
    queue.schedule('p1');
    await vi.advanceTimersByTimeAsync(3000);
    queue.undo('p1');
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS * 2);
    expect(remove).not.toHaveBeenCalled();
    expect(get(queue.hidden).has('p1')).toBe(false);
    expect(get(queue.toasts)).toEqual([]);
  });

  it('restores the page and shows an error toast when the request fails', async () => {
    remove.mockRejectedValueOnce(new Error('500'));
    queue.schedule('p1');
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS);
    expect(get(queue.hidden).has('p1')).toBe(false);
    const toasts = get(queue.toasts);
    expect(toasts).toHaveLength(1);
    expect(toasts[0].kind).toBe('error');
    await vi.advanceTimersByTimeAsync(ERROR_TOAST_MS);
    expect(get(queue.toasts)).toEqual([]);
  });

  it('keeps separate timers and toasts for several deletes', async () => {
    queue.schedule('p1');
    await vi.advanceTimersByTimeAsync(2000);
    queue.schedule('p2');
    expect(get(queue.toasts).map((t) => t.pageId)).toEqual(['p1', 'p2']);
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS - 2000);
    expect(remove).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith('p1', undefined);
    queue.undo('p2');
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('counts deletes the server confirmed', async () => {
    queue.schedule('p1');
    expect(get(queue.committed)).toBe(0);
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS);
    expect(get(queue.committed)).toBe(1);
    remove.mockRejectedValueOnce(new Error('500'));
    queue.schedule('p2');
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS);
    expect(get(queue.committed)).toBe(1);
  });

  it('notify shows a self-dismissing error toast', async () => {
    queue.notify("Couldn't load your map.");
    expect(get(queue.toasts)[0]).toMatchObject({ kind: 'error', message: "Couldn't load your map." });
    await vi.advanceTimersByTimeAsync(ERROR_TOAST_MS);
    expect(get(queue.toasts)).toEqual([]);
  });

  it('ignores a second delete of the same page while one is pending', () => {
    queue.schedule('p1');
    queue.schedule('p1');
    expect(get(queue.toasts)).toHaveLength(1);
  });

  it('flush sends pending deletes immediately (tab closing)', async () => {
    queue.schedule('p1');
    queue.schedule('p2');
    expect(queue.flush({ keepalive: true })).toBe(2);
    await vi.advanceTimersByTimeAsync(0);
    expect(remove).toHaveBeenCalledWith('p1', { keepalive: true });
    expect(remove).toHaveBeenCalledWith('p2', { keepalive: true });
    await vi.advanceTimersByTimeAsync(DELETE_DELAY_MS);
    expect(remove).toHaveBeenCalledTimes(2);
  });
});
