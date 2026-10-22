const tests = [
  ['probe_run', 'Microsoft C++ ABI: размеры классов, виртуальные вызовы, thiscall'],
  ['probe_inalloca', 'Передача объектов: копирование, возврат значений, деструкторы'],
  ['probe_geometry', 'Код движка: пересечение луча с плоскостью'],
  ['probe_seer', 'Оригинальный SeeR: арифметика, int/double callbacks, пауза, ошибки'],
  ['probe_varargs', 'Varargs: смешанные типы, структуры, вызовы через указатель, рекурсия'],
];
const button = document.querySelector('#run');
const status = document.querySelector('#status');
const results = document.querySelector('#results');
let instance;
async function run() {
  button.disabled = true;
  results.replaceChildren();
  try {
    if (!instance) {
      const response = await fetch('titbit-probe.wasm');
      if (!response.ok) throw new Error(`Загрузка Wasm: HTTP ${response.status}`);
      const module = await WebAssembly.compile(await response.arrayBuffer());
      if (WebAssembly.Module.imports(module).length) throw new Error('Неожиданные импорты Wasm');
      instance = await WebAssembly.instantiate(module);
    }
    for (const [name, label] of tests) {
      const code = instance.exports[name]();
      const row = document.createElement('tr');
      const title = document.createElement('td');
      const result = document.createElement('td');
      title.textContent = label;
      result.textContent = code === 0 ? 'PASS' : `FAIL (${code})`;
      result.className = code === 0 ? 'pass' : 'fail';
      row.append(title, result);
      results.append(row);
      if (code !== 0) throw new Error(`${name}: код ${code}`);
    }
    status.textContent = `Все ${tests.length} проверок пройдены. Платформенный слой и первая сцена пока не перенесены.`;
    document.documentElement.dataset.result = 'passed';
  } catch (error) {
    status.textContent = `Ошибка: ${error.message}`;
    document.documentElement.dataset.result = 'failed';
  } finally {
    button.disabled = false;
  }
}
button.addEventListener('click', run);
run();
