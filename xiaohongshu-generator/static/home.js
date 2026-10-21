'use strict';
(() => {
  document.getElementById('gallery-grid').addEventListener('click', e => {
    const sample = e.target.closest('[data-sample]');
    if (sample) Tuka.sample(sample.dataset.sample, sample.dataset.name);
    const select = e.target.closest('[data-select]');
    if (select) Tuka.event('template_select', select.dataset.select);
  });
  document.getElementById('show-all').addEventListener('click', e => {
    const button = e.currentTarget;
    const expanded = button.getAttribute('aria-expanded') === 'true';
    const grid = document.getElementById('gallery-grid');
    if (!expanded) {
      grid.append(document.getElementById('more-styles').content.cloneNode(true));
      button.textContent = '收起更多样式 −';
    } else {
      [...grid.children].slice(12).forEach(node => node.remove());
      button.textContent = `查看全部 ${button.dataset.total} 款样式 ＋`;
    }
    button.setAttribute('aria-expanded', String(!expanded));
  });
})();
