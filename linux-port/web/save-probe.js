import { SaveStore, createSaveRuntime } from './saves.js';

const controls = document.querySelector('#controls');
const status = document.querySelector('#status');
const value = document.querySelector('#value');
const slot = document.querySelector('#slot');
const store = new SaveStore({ name: 'titbit-save-probe' });
let runtime;
let busy = false;
const selected = () => Number(slot.value);
const showState = () => { value.value = new DataView(runtime.getState().buffer).getInt32(44, true); };

async function action(operation) {
  if (busy) return;
  busy = true;
  controls.disabled = true;
  try {
    status.textContent = await operation();
    document.documentElement.dataset.result = 'passed';
  } catch (error) {
    status.textContent = `Ошибка: ${error.message}`;
    document.documentElement.dataset.result = 'failed';
  } finally {
    busy = false;
    controls.disabled = !runtime;
  }
}

document.querySelector('#save').addEventListener('click', () => action(async () => {
  const number = Number(value.value);
  if (!value.value || !Number.isInteger(number) || number < -2147483648 || number > 2147483647) {
    throw new Error('Введите целое число от −2147483648 до 2147483647');
  }
  const bytes = runtime.getState();
  bytes.fill(0, 0, 32);
  bytes.set(new TextEncoder().encode(new Date().toISOString()), 0);
  new DataView(bytes.buffer).setInt32(44, number, true);
  runtime.setState(bytes);
  await runtime.save(selected());
  return `Слот ${selected() + 1} сохранён. Можно перезагрузить страницу и загрузить его снова.`;
}));

document.querySelector('#load').addEventListener('click', () => action(async () => {
  await runtime.load(selected());
  showState();
  return `Слот ${selected() + 1} загружен.`;
}));

document.querySelector('#download').addEventListener('click', () => action(async () => {
  const blob = await store.exportFile(selected());
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `titbit-slot-${selected() + 1}.sav`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return 'Файл сохранения подготовлен для скачивания.';
}));

document.querySelector('#import').addEventListener('change', event => {
  const file = event.target.files[0];
  event.target.value = '';
  if (file) action(async () => {
    await store.importFile(selected(), file);
    await runtime.load(selected());
    showState();
    return `Файл импортирован в слот ${selected() + 1} и загружен.`;
  });
});

action(async () => {
  const response = await fetch('titbit-save-probe.wasm');
  if (!response.ok) throw new Error(`Загрузка Wasm: HTTP ${response.status}`);
  await store.open();
  runtime = await createSaveRuntime(await response.arrayBuffer(), store);
  return 'Готово. Сохраните число в слот, перезагрузите страницу и нажмите «Загрузить».';
});
