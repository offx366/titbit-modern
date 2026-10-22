// Persistent copies of verified, bundled assets. Separate from save slots.
export class AssetStore {
  constructor({baseURL = new URL('.', import.meta.url), cacheStorage = globalThis.caches,
    fetcher = globalThis.fetch.bind(globalThis), onStatus = () => {}, onCacheError = () => {}} = {}) {
    this.baseURL = new URL(baseURL);
    this.cacheName = `titbit-assets-v1:${this.baseURL.pathname}`;
    this.cacheStorage = cacheStorage;
    this.fetcher = fetcher;
    this.onStatus = onStatus;
    this.onCacheError = onCacheError;
    this.opening = null;
  }

  async cache() {
    if (!this.opening) {
      this.opening = Promise.resolve().then(() => {
        if (!this.cacheStorage) throw new Error('CacheStorage unavailable');
        return this.cacheStorage.open(this.cacheName);
      })
        .catch(error => { this.onCacheError(error); return null; });
    }
    return this.opening;
  }

  key(file) {
    const url = new URL(file.url, this.baseURL);
    url.searchParams.set('sha256', file.sha256);
    return url.href;
  }

  async verify(bytes, file) {
    if (file.size !== undefined && bytes.length !== file.size) throw new Error(`Неверный размер ${file.name}`);
    if (file.sha256) {
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
        byte => byte.toString(16).padStart(2, '0')).join('');
      if (hash !== file.sha256) throw new Error(`Повреждён файл ${file.name}`);
    }
    return bytes;
  }

  async read(file) {
    // Development server files have no hash and can change without a manifest.
    const cache = file.sha256 ? await this.cache() : null;
    const key = file.sha256 ? this.key(file) : null;
    if (cache) {
      try {
        const response = await cache.match(key);
        if (response) {
          this.onStatus(`Из кэша: ${file.name}…`);
          const bytes = new Uint8Array(await response.arrayBuffer());
          try { return await this.verify(bytes, file); }
          catch { await cache.delete(key); } // Repair only this invalid cached file.
        }
      } catch (error) { this.onCacheError(error); }
    }
    this.onStatus(`Загрузка ${file.name}…`);
    const response = await this.fetcher(new URL(file.url, this.baseURL).href);
    if (!response.ok) throw new Error(`Не удалось прочитать ${file.name}`);
    const bytes = await this.verify(new Uint8Array(await response.arrayBuffer()), file);
    if (cache) {
      try { await cache.put(key, new Response(bytes)); }
      catch (error) { this.onCacheError(error); } // A full/disabled cache must not prevent play.
    }
    return bytes;
  }
}
