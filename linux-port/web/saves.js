// Browser storage for the original game's raw QuestState format.
export const SAVE_SIZE = 408;
const STORE = 'slots';

function validateSlot(slot) {
  if (!Number.isInteger(slot) || slot < 0 || slot > 99) throw new RangeError('Неверный слот сохранения');
}

function copyBytes(data) {
  if (!(data instanceof Uint8Array) || data.byteLength !== SAVE_SIZE) {
    throw new Error(`Сохранение должно содержать ровно ${SAVE_SIZE} байт`);
  }
  return new Uint8Array(data);
}

async function digest(data) {
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
}

export class SaveStore {
  constructor({ name = 'titbit-saves', indexedDB = globalThis.indexedDB } = {}) {
    this.name = name;
    this.indexedDB = indexedDB;
    this.connection = null;
    this.opening = null;
  }

  async open() {
    if (this.connection) return this.connection;
    if (!this.indexedDB) throw new Error('Хранилище сохранений недоступно в этом браузере');
    if (!this.opening) {
      this.opening = new Promise((resolve, reject) => {
        const request = this.indexedDB.open(this.name, 1);
        let rejected = false;
        request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'slot' });
        request.onerror = () => reject(request.error);
        request.onblocked = () => {
          rejected = true;
          reject(new Error('Закройте другие вкладки игры и повторите загрузку хранилища'));
        };
        request.onsuccess = () => {
          const db = request.result;
          if (rejected) { db.close(); return; }
          this.connection = db;
          db.onversionchange = () => this.close();
          db.onclose = () => { if (this.connection === db) this.connection = null; };
          resolve(db);
        };
      }).finally(() => { this.opening = null; });
    }
    return this.opening;
  }

  close() {
    this.connection?.close();
    this.connection = null;
  }

  async transaction(mode, operation) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      // Strict durability asks for persistent writes before reporting success.
      const tx = db.transaction(STORE, mode, { durability: 'strict' });
      let request;
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = () => reject(tx.error || new Error('Запись сохранения отменена'));
      tx.onerror = () => {}; // Abort is the authoritative failure event.
      try { request = operation(tx.objectStore(STORE)); }
      catch (error) { tx.abort(); reject(error); }
    });
  }

  async write(slot, data) {
    validateSlot(slot);
    const bytes = copyBytes(data); // Snapshot before the first asynchronous step.
    const record = { slot, format: 1, bytes, sha256: await digest(bytes), savedAt: Date.now() };
    await this.transaction('readwrite', store => store.put(record));
    return { slot, savedAt: record.savedAt };
  }

  async read(slot) {
    validateSlot(slot);
    const record = await this.transaction('readonly', store => store.get(slot));
    if (!record) return null;
    const bytes = copyBytes(record.bytes);
    if (record.format !== 1 || record.sha256 !== await digest(bytes)) {
      throw new Error('Сохранение повреждено или имеет неподдерживаемый формат');
    }
    return bytes;
  }

  async list() {
    const records = await this.transaction('readonly', store => store.getAll());
    return records.map(({ slot, savedAt }) => ({ slot, savedAt }));
  }

  async remove(slot) {
    validateSlot(slot);
    await this.transaction('readwrite', store => store.delete(slot));
  }

  async importFile(slot, file) {
    if (file.size !== SAVE_SIZE) throw new Error(`Сохранение должно содержать ровно ${SAVE_SIZE} байт`);
    return this.write(slot, new Uint8Array(await file.arrayBuffer()));
  }

  async exportFile(slot) {
    const bytes = await this.read(slot);
    if (!bytes) throw new Error('В этом слоте нет сохранения');
    return new Blob([bytes], { type: 'application/octet-stream' });
  }
}

// A narrow CRT adapter for the serializer probe, not a general game filesystem.
// SaveStore persists complete files asynchronously after SaveGame returns.
export async function createSaveRuntime(wasmBytes, store = new SaveStore()) {
  let exports;
  let file = null;
  let input = null;
  let output = null;
  const memory = () => new Uint8Array(exports.memory.buffer);
  const string = address => {
    const bytes = memory();
    let end = address;
    while (end < bytes.length && bytes[end]) ++end;
    return new TextDecoder().decode(bytes.subarray(address, end));
  };
  const imports = { env: {
    fopen(path, mode) {
      if (file || string(path) !== 'browser.sav') return 0;
      const access = string(mode);
      if (access !== 'wb' && access !== 'rb') return 0;
      if (access === 'rb' && !input) return 0;
      file = { access, position: 0, bytes: access === 'rb' ? input : new Uint8Array(SAVE_SIZE) };
      return 1;
    },
    fwrite(address, size, count, handle) {
      const length = size * count;
      if (handle !== 1 || file?.access !== 'wb' || size <= 0 || count < 0 ||
          file.position + length > SAVE_SIZE || address < 0 || address + length > memory().length) return 0;
      file.bytes.set(memory().subarray(address, address + length), file.position);
      file.position += length;
      return count;
    },
    fread(address, size, count, handle) {
      const length = size * count;
      if (handle !== 1 || file?.access !== 'rb' || size <= 0 || count < 0 ||
          file.position + length > file.bytes.length || address < 0 || address + length > memory().length) return 0;
      memory().set(file.bytes.subarray(file.position, file.position + length), address);
      file.position += length;
      return count;
    },
    fclose(handle) {
      if (handle !== 1 || !file) return -1;
      if (file.access === 'wb' && file.position === SAVE_SIZE) output = file.bytes;
      file = null;
      return 0;
    },
  } };
  const module = await WebAssembly.compile(wasmBytes);
  const instance = await WebAssembly.instantiate(module, imports);
  exports = instance.exports;
  // Explicit reactor startup: otherwise wasm-ld may wrap each export with
  // constructor calls, resetting QuestState before every save/read.
  exports.__wasm_call_ctors();
  if (exports.save_state_size() !== SAVE_SIZE) throw new Error('Размер состояния Wasm не совпадает с форматом сохранений');
  exports.save_state_reset();
  return {
    getState() {
      const address = exports.save_state_address();
      return memory().slice(address, address + SAVE_SIZE);
    },
    setState(data) { memory().set(copyBytes(data), exports.save_state_address()); },
    async save(slot) {
      output = null;
      if (exports.save_write() !== 1 || !output) throw new Error('Движок не смог записать сохранение');
      return store.write(slot, output);
    },
    async load(slot) {
      // Do not touch live engine state unless a complete, verified file exists.
      input = await store.read(slot);
      if (!input) throw new Error('В этом слоте нет сохранения');
      try {
        if (exports.save_read() !== 1) throw new Error('Движок не смог загрузить сохранение');
      } finally { input = null; }
    },
  };
}
