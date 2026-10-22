// Static hosts such as GitHub Pages cannot supply COOP/COEP themselves. Wait
// for an isolated navigation before loading Emscripten or accepting game data.
const status = document.querySelector('#status');
const reloadKey = `titbit-isolation:${new URL('.', import.meta.url).pathname}`;
async function isolate() {
  if (globalThis.crossOriginIsolated) {
    sessionStorage.removeItem(reloadKey);
    return true;
  }
  if (!globalThis.isSecureContext || !navigator.serviceWorker) {
    throw new Error('Для запуска нужен HTTPS (или localhost) и поддержка service worker.');
  }
  status.textContent = 'Подготовка запуска…';
  const workerURL = new URL('./isolation-worker.js', import.meta.url);
  const controlled = () => navigator.serviceWorker.controller?.scriptURL === workerURL.href;
  await navigator.serviceWorker.register(workerURL, {
    scope: './', updateViaCache: 'none'
  });
  if (!controlled()) {
    await new Promise((resolve, reject) => {
      const changed = () => {
        if (!controlled()) return;
        clearTimeout(timer);
        navigator.serviceWorker.removeEventListener('controllerchange', changed);
        resolve();
      };
      const timer = setTimeout(() => {
        navigator.serviceWorker.removeEventListener('controllerchange', changed);
        reject(new Error('Не удалось подготовить запуск. Разрешите service worker для этого сайта.'));
      }, 20000);
      navigator.serviceWorker.addEventListener('controllerchange', changed);
      changed();
    });
  }
  if (sessionStorage.getItem(reloadKey)) {
    throw new Error('Браузер не разрешил запуск потоков игры. Попробуйте обычное окно Chromium или Firefox.');
  }
  sessionStorage.setItem(reloadKey, '1');
  location.reload();
  return false;
}

try {
  if (await isolate()) {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = new URL('./titbit.js', import.meta.url);
      script.onload = resolve;
      script.onerror = () => reject(new Error('Не удалось загрузить движок. Обновите страницу.'));
      document.head.append(script);
    });
    await import('./game.js');
  }
} catch (error) {
  console.error(error);
  status.textContent = `Ошибка: ${error.message || error}`;
}
