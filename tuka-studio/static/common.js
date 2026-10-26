'use strict';
(() => {
  const dialog = document.getElementById('image-dialog');
  const images = document.getElementById('dialog-images');
  function event(name, style) {
    fetch('/api/events', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({event: name, style}), keepalive: true}).catch(() => {});
  }
  const navigation = document.getElementById('dialog-navigation');
  const previous = document.getElementById('dialog-previous');
  const next = document.getElementById('dialog-next');
  let gallerySources = [];
  let galleryIndex = null;
  let galleryTitle = '';
  function drawGallery() {
    const img = document.createElement('img');
    img.src = gallerySources[galleryIndex];
    img.alt = galleryTitle + ' · 第 ' + (galleryIndex + 1) + ' 张';
    img.width = 1242; img.height = 1660;
    images.replaceChildren(img);
    images.scrollTop = 0; dialog.scrollTop = 0;
    document.getElementById('dialog-position').textContent = (galleryIndex + 1) + ' / ' + gallerySources.length;
    previous.disabled = galleryIndex === 0;
    next.disabled = galleryIndex === gallerySources.length - 1;
  }
  function moveGallery(offset) {
    if (galleryIndex === null) return;
    const index = galleryIndex + offset;
    if (index < 0 || index >= gallerySources.length) return;
    galleryIndex = index; drawGallery();
  }
  function showImages(title, sources, startIndex = null) {
    document.getElementById('dialog-title').textContent = title;
    gallerySources = sources;
    galleryTitle = title;
    galleryIndex = Number.isInteger(startIndex) ? Math.max(0, Math.min(startIndex, sources.length - 1)) : null;
    navigation.hidden = galleryIndex === null;
    if (galleryIndex !== null) {
      drawGallery();
    } else {
      images.replaceChildren(...sources.map((src, index) => {
        const img = document.createElement('img');
        img.src = src;
        img.alt = title + (sources.length > 1 ? (index ? '内容页' : '封面') : '');
        img.width = 1242; img.height = 1660;
        return img;
      }));
    }
    dialog.showModal();
  }
  previous.addEventListener('click', () => moveGallery(-1));
  next.addEventListener('click', () => moveGallery(1));
  document.addEventListener('keydown', e => {
    if (!dialog.open || galleryIndex === null || e.altKey || e.ctrlKey || e.metaKey || e.target.closest('input,textarea,select,[contenteditable]')) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault(); moveGallery(e.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  dialog.addEventListener('close', () => { gallerySources = []; galleryIndex = null; images.replaceChildren(); navigation.hidden = true; });
  function sample(style, name) {
    event('sample_view', style);
    showImages(name + ' · 真实模板样例', ['/static/samples/' + style + '-full.webp?v=7', '/static/samples/' + style + '-content.webp?v=7']);
  }
  document.getElementById('close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', e => { if (e.target === dialog) {
    const rect = dialog.getBoundingClientRect();
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) dialog.close();
  }});
  window.Tuka = {event, sample, showImages};
})();
