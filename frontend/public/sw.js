/* Verqac service worker: shows push notifications even when no Verqac tab is open. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (_) { d = { title: event.data && event.data.text() }; }
  const show = self.registration.showNotification(d.title || 'Verqac', {
    body: d.body || '',
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    tag: d.tag,
    renotify: true,            // sound and pop-up again even if a notification with this tag is shown
    requireInteraction: true,  // stays on screen until the engineer clicks or closes it
    vibrate: [200, 100, 200],
    dir: 'auto',
    data: { url: d.url || '/inbox' },
  });
  // open Verqac tabs play the chime and refresh their bell
  const tell = self.clients.matchAll({ type: 'window' }).then((cs) => cs.forEach((c) => c.postMessage({ type: 'verqac-push' })));
  event.waitUntil(Promise.all([show, tell]));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(event.notification.data && event.notification.data.url || '/inbox', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((cs) => {
    for (const c of cs) {
      if (new URL(c.url).origin === self.location.origin) return c.focus().then(() => c.navigate(url));
    }
    return self.clients.openWindow(url);
  }));
});
