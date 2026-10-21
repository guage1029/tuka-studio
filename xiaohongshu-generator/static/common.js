'use strict';
(() => {
  const dialog = document.getElementById('image-dialog');
  const images = document.getElementById('dialog-images');
  function event(name, style) {
    fetch('/api/events', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({event: name, style}), keepalive: true}).catch(() => {});
  }
  function showImages(title, sources) {
    document.getElementById('dialog-title').textContent = title;
    images.replaceChildren(...sources.map((src, index) => {
      const img = document.createElement('img');
      img.src = src;
      img.alt = title + (sources.length > 1 ? (index ? '内容页' : '封面') : '');
      img.width = 1242; img.height = 1660;
      return img;
    }));
    dialog.showModal();
  }
  function sample(style, name) {
    event('sample_view', style);
    showImages(name + ' · 真实模板样例', ['/static/samples/' + style + '-full.webp', '/static/samples/' + style + '-content.webp']);
  }
  document.getElementById('close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', e => { if (e.target === dialog) {
    const rect = dialog.getBoundingClientRect();
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) dialog.close();
  }});
  window.Tuka = {event, sample, showImages};
})();
