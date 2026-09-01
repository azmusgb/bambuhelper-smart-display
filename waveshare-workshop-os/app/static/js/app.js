(() => {
  'use strict';

  const views = ['home', 'printer', 'workshop', 'connections', 'device', 'system'];
  const nav = document.querySelector('[data-nav]');
  const status = document.querySelector('#status');
  const clock = document.querySelector('#clock');

  function setView(view) {
    if (!views.includes(view)) view = 'home';
    document.querySelectorAll('[data-view]').forEach((el) => {
      el.hidden = el.dataset.view !== view;
    });
    document.querySelectorAll('[data-route]').forEach((el) => {
      el.setAttribute('aria-current', el.dataset.route === view ? 'page' : 'false');
    });
    history.replaceState(null, '', `#${view}`);
  }

  nav?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-route]');
    if (button) setView(button.dataset.route);
  });

  function updateClock() {
    if (clock) clock.textContent = new Intl.DateTimeFormat(undefined, {
      hour: 'numeric', minute: '2-digit', second: '2-digit'
    }).format(new Date());
  }

  if (status) status.textContent = 'Online';
  setView(location.hash.slice(1) || 'home');
  updateClock();
  window.setInterval(updateClock, 1000);
})();
