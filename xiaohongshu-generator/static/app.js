'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const content = $('content');
  const style = $('style-select');
  let slides = null;
  let images = [];
  let revision = 0;
  let pending = null;
  let lastImageEditor = null;
  let modelRequest = null;
  let modelsLoaded = false;
  const closeIcon = () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', 'm6 6 12 12M6 18 18 6'); svg.append(path); return svg;
  };
  function status(message = '', kind = '') {
    $('status').textContent = message;
    $('status').dataset.kind = kind;
  }
  function changed() {
    revision++;
    if (images.length) {
      images = [];
      $('results').replaceChildren();
      $('results-section').hidden = true;
      $('editor').hidden = false;
      $('download-all').hidden = true;
      $('edit-cards').hidden = true;
      $('render').textContent = '⑤ 生成图卡';
      status('文案或样式已更改，确认后请重新渲染。');
    }
  }
  function fieldError(input, id, message) {
    $(id).textContent = message;
    input.setAttribute('aria-invalid', String(Boolean(message)));
  }
  function validKey(check = true) {
    const key = $('api-key').value.trim();
    const message = /^[\x21-\x7E]{1,512}$/.test(key) ? '' : '请填写有效的 API Key，不含空格或换行。';
    if (check) fieldError($('api-key'), 'key-error', message);
    return message ? null : key;
  }
  function config(check = true) {
    const key = validKey(check);
    const selected = modelsLoaded && $('model').value;
    if (check) {
      fieldError($('model'), 'model-error', selected ? '' : '请刷新模型列表，并选择要使用的模型。');
      if (!key || !selected) { $('model-config').open = true; (key ? $('refresh-models') : $('api-key')).focus(); }
    }
    return key && selected ? {provider: $('provider').value, api_key: key, model: selected} : null;
  }
  function resetModels() {
    if (modelRequest) modelRequest.abort();
    modelRequest = null;
    modelsLoaded = false;
    $('model').replaceChildren(new Option('先输入 Key，再刷新模型列表', ''));
    $('model').size = 1;
    $('model').disabled = true;
    $('refresh-models').disabled = Boolean(pending);
    $('save-config').disabled = Boolean(pending);
    $('refresh-models').textContent = '刷新模型列表';
    $('generate').disabled = Boolean(pending);
    $('model-status').textContent = '';
    $('model-selection').textContent = '';
    fieldError($('model'), 'model-error', '');
  }
  $('refresh-models').addEventListener('click', async () => {
    const apiKey = validKey();
    if (!apiKey) { $('api-key').focus(); return; }
    const controller = new AbortController();
    modelRequest = controller;
    const timer = setTimeout(() => controller.abort(), 20000);
    $('refresh-models').disabled = true;
    $('save-config').disabled = true;
    $('refresh-models').textContent = '正在获取……';
    $('generate').disabled = true;
    $('model-status').textContent = '正在获取模型列表……';
    fieldError($('model'), 'model-error', '');
    const previous = $('model').value;
    try {
      const result = await requestJSON('/api/models', {provider: $('provider').value, api_key: apiKey}, controller.signal);
      if (modelRequest !== controller) return;
      $('model').replaceChildren(new Option('请选择一个模型', ''), ...result.models.map(id => new Option(id, id)));
      $('model').size = 1;
      $('model').disabled = false;
      if (result.models.includes(previous)) $('model').value = previous;
      modelsLoaded = true;
      $('model-selection').textContent = $('model').value ? `已选择：${$('model').value}` : '';
      $('model-status').textContent = result.message || '';
      revision++;
      if (!previous) $('model').focus();
    } catch (error) {
      if (modelRequest === controller) {
        const message = error.name === 'AbortError' ? '获取模型列表超时，请重试。' : error.message;
        fieldError($('model'), 'model-error', message);
        $('model-status').textContent = modelsLoaded ? '刷新失败，保留上次获取的模型列表。' : '未获取到模型列表，请检查 Key 后重试。';
      }
    } finally {
      clearTimeout(timer);
      if (modelRequest === controller) {
        modelRequest = null;
        $('refresh-models').disabled = Boolean(pending);
        $('save-config').disabled = Boolean(pending);
        $('refresh-models').textContent = '刷新模型列表';
        $('generate').disabled = Boolean(pending);
      }
    }
  });
  function validateContent() {
    const message = [...content.value.trim()].length < 50 ? '请输入至少 50 字的内容。' : '';
    fieldError(content, 'content-error', message);
    return !message;
  }
  function busy(value) {
    $('generate').disabled = value || Boolean(modelRequest);
    $('refresh-models').disabled = value || Boolean(modelRequest);
    $('save-config').disabled = value || Boolean(modelRequest);
    $('render').disabled = value;
    $('download-all').disabled = value;
    document.querySelectorAll('[data-regenerate]').forEach(button => { button.disabled = value; });
    $('cancel-task').hidden = !value;
  }
  async function requestJSON(path, body, signal) {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal});
    let result;
    try { result = await response.json(); } catch { throw new Error('服务暂不可用，请稍后重试。'); }
    if (!response.ok) throw new Error(result.error || '处理失败，请稍后重试。');
    return result;
  }
  async function task(label, action, apply) {
    if (pending) return;
    const controller = new AbortController();
    const current = {controller, revision};
    pending = current;
    const timer = setTimeout(() => controller.abort(), 100000);
    busy(true); status(label, 'loading');
    try {
      const result = await action(controller.signal);
      if (pending !== current) return;
      if (revision !== current.revision) {
        status('处理期间内容已变化，已保留当前编辑。请按当前内容重试。');
        return;
      }
      apply(result);
    } catch (error) {
      if (pending === current) {
        status(error.name === 'AbortError' ? '操作已取消或超时，当前内容已保留。' : error.message, 'error');
      }
    } finally {
      clearTimeout(timer);
      if (pending === current) { pending = null; busy(false); }
    }
  }
  $('cancel-task').addEventListener('click', () => { if (pending) pending.controller.abort(); });
  function invalidateInput() {
    changed();
    $('char-count').textContent = content.value.length.toLocaleString('en-US') + ' / 20,000';
  }
  content.addEventListener('input', invalidateInput);
  content.addEventListener('blur', () => { if (content.value) validateContent(); });
  $('provider').addEventListener('change', () => {
    revision++;
    $('api-key').value = '';
    $('api-key').type = 'password';
    $('toggle-key').setAttribute('aria-label', '显示 Key');
    $('toggle-key').setAttribute('aria-pressed', 'false');
    fieldError($('api-key'), 'key-error', '');
    resetModels();
  });
  $('api-key').addEventListener('input', () => { revision++; resetModels(); fieldError($('api-key'), 'key-error', ''); });
  $('model').addEventListener('change', () => {
    revision++;
    fieldError($('model'), 'model-error', '');
    $('model-selection').textContent = $('model').value ? `已选择：${$('model').value}` : '';
  });
  let openingModelMenu = false;
  $('model').addEventListener('mousedown', event => {
    openingModelMenu = $('model').size === 1;
    if (openingModelMenu && !$('model').disabled) {
      event.preventDefault();
      $('model').size = $('model').options.length;
      $('model').focus();
    }
  });
  $('model').addEventListener('click', () => {
    if (!openingModelMenu && $('model').value) $('model').size = 1;
    openingModelMenu = false;
  });
  $('model').addEventListener('keydown', event => {
    if (['Enter', ' '].includes(event.key) || ($('model').size === 1 && ['ArrowDown', 'ArrowUp'].includes(event.key))) {
      event.preventDefault();
      $('model').size = $('model').size === 1 ? $('model').options.length : 1;
    } else if (event.key === 'Escape') {
      event.preventDefault();
      $('model').size = 1;
    }
  });
  $('model').addEventListener('blur', () => { $('model').size = 1; });
  resetModels();
  $('config-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!config()) return;
    $('api-key').type = 'password';
    $('toggle-key').setAttribute('aria-label', '显示 Key');
    $('toggle-key').setAttribute('aria-pressed', 'false');
    $('model').size = 1;
    $('model-config').open = false;
    $('model-config').querySelector('summary').focus();
  });
  $('toggle-key').addEventListener('click', () => {
    const show = $('api-key').type === 'password';
    $('api-key').type = show ? 'text' : 'password';
    $('toggle-key').setAttribute('aria-label', show ? '隐藏 Key' : '显示 Key');
    $('toggle-key').setAttribute('aria-pressed', String(show));
  });
  $('use-example').addEventListener('click', () => {
    content.value = '给灵感留白：建立一个可持续的创作习惯\n\n灵感并不总在你坐到书桌前出现。把每天看到的细节、读到的句子和突然冒出的想法记在同一个地方，不急着判断价值。每天留出十五分钟，选一个问题，写下你真实的观察。\n\n初稿先求完整，再求漂亮。一次只打磨一个核心观点，用具体的故事和可核对的数据支撑它。删掉没有信息量的形容词，把长句拆短，给读者留出理解的空间。\n\n写完后大声读一遍，再检查事实和来源。把内容整理成清楚的标题、几个要点和一个行动建议。定期回看自己的素材，看看哪些话题值得继续。慢一点，持续地做，表达就会逐渐长出自己的样子。';
    invalidateInput(); validateContent(); content.focus();
  });
  $('generate').addEventListener('click', () => {
    const validContent = validateContent();
    const settings = config();
    if (!validContent || !settings) { if (!validContent && settings) content.focus(); return; }
    $('model-config').open = false;
    const body = {content: content.value, config: settings, style: style.value};
    task('正在整理文案，通常需要几秒。',
      signal => requestJSON('/preview', body, signal), result => {
        slides = result.slides_data;
        changed();
        showEditor();
        let message = '文案已整理。请检查事实、标题和要点，确认后渲染图片。';
        const selection = result.image_summary;
        if (selection?.candidates) {
          message += `\n已根据图片说明和上下文，从 ${selection.candidates} 张候选配图中采用 ${selection.used} 张，其余未使用。`;
          if (selection.failed) message += `其中 ${selection.failed} 张选中图片无法安全获取，已跳过，可在编辑区补图。`;
        }
        status(message);
      });
  });
  style.addEventListener('change', () => {
    const hadImages = images.length > 0;
    changed();
    document.querySelectorAll('input[name="style-choice"]').forEach(option => {
      option.checked = option.value === style.value;
      option.closest('.style-option').classList.toggle('is-selected', option.checked);
    });
    Tuka.event('template_select', style.value);
    if (hadImages && !pending) render();
  });
  document.querySelectorAll('input[name="style-choice"]').forEach(option => option.addEventListener('change', () => {
    if (!option.checked) return;
    style.value = option.value;
    style.dispatchEvent(new Event('change', {bubbles: true}));
  }));
  function placeStylePreview(event) {
    const image = event.currentTarget.querySelector('.style-preview img');
    if (!image.hasAttribute('src')) image.src = image.dataset.src;
    const rect = event.currentTarget.getBoundingClientRect();
    const width = Math.min(190, window.innerWidth - 32);
    const height = width * (1660 / 1242) + 42;
    const rightSpace = window.innerWidth - rect.right;
    const left = rightSpace > width + 16 ? rect.right + 8 : rect.left > width + 16 ? rect.left - width - 8 : Math.max(16, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 16));
    const top = Math.max(16, Math.min(rect.top + rect.height / 2 - height / 2, window.innerHeight - height - 16));
    event.currentTarget.style.setProperty('--preview-left', left + 'px');
    event.currentTarget.style.setProperty('--preview-top', top + 'px');
  }
  document.querySelectorAll('.style-option').forEach(option => {
    option.addEventListener('pointerenter', placeStylePreview);
    option.addEventListener('focusin', placeStylePreview);
  });
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function button(text, className, action) {
    const element = node('button', className, text); element.type = 'button'; element.addEventListener('click', action); return element;
  }
  function field(parent, labelText, value, max, apply, multiline = false) {
    const label = node('label', 'card-field');
    const caption = node('span', 'visually-hidden', labelText);
    const input = node(multiline ? 'textarea' : 'input');
    if (!multiline) input.type = 'text'; else input.rows = 2;
    input.value = value; input.maxLength = max; input.placeholder = labelText.split(' · ')[0];
    input.addEventListener('input', () => { apply(input.value); changed(); });
    label.append(caption, input); parent.append(label); return input;
  }
  function showEditor() {
    $('empty-state').hidden = true;
    $('editor').hidden = false;
    $('results-section').hidden = true;
    $('edit-cards').hidden = true;
    $('download-all').hidden = true;
    $('render').textContent = '⑤ 生成图卡';
    $('render-actions').hidden = false;
    $('output-count').textContent = (slides.slides.length + 1) + ' 张图卡';
    $('output-count').hidden = false;
    $('card-stage').style.setProperty('--card-rows', Math.ceil((slides.slides.length + 1) / 4));
    $('editor').replaceChildren();
    [slides, ...slides.slides].forEach((card, index) => {
      const article = node('article', 'edit-card');
      article.style.setProperty('--card-order', index);
      article.setAttribute('aria-label', index ? '编辑内容页 ' + index : '编辑封面');
      const heading = node('div', 'edit-card-heading');
      heading.append(node('h3', '', index ? '内容页 ' + String(index).padStart(2, '0') : '封面'));
      const regenerate = button('重新生成此页', 'plain-button', () => regenerateCard(index));
      regenerate.dataset.regenerate = String(index); regenerate.disabled = Boolean(pending);
      heading.append(regenerate); article.append(heading);
      const copy = node('div', 'card-copy'); article.append(copy);
      if (!index) {
        field(copy, '封面标题 · 最多 24 字', slides.cover_title, 24, value => { slides.cover_title = value; }, true).className = 'card-title';
        field(copy, '副标题 · 最多 80 字', slides.cover_subtitle, 80, value => { slides.cover_subtitle = value; }, true).className = 'card-subtitle';
        field(copy, '标签 · 用逗号分隔，最多 5 个，每个 10 字', slides.cover_tags.join('，'), 60, value => { slides.cover_tags = value.split(/[,，]/).map(tag => tag.trim()).filter(Boolean); }).className = 'card-tags';
      } else {
        field(copy, '标题 · 最多 24 字', card.title, 24, value => { card.title = value; }, true).className = 'card-title';
        const points = node('div', 'card-points'); copy.append(points);
        function drawPoints() {
          points.replaceChildren();
          card.content.forEach((point, pointIndex) => {
            const row = node('div', 'point-row');
            field(row, '要点 ' + (pointIndex + 1) + ' · 最多 50 字', point, 50, value => { card.content[pointIndex] = value; }, true);
            const remove = button('', 'icon-button', () => { card.content.splice(pointIndex, 1); changed(); drawPoints(); add.disabled = false; points.querySelector('textarea')?.focus(); });
            remove.setAttribute('aria-label', '删除要点 ' + (pointIndex + 1)); remove.append(closeIcon());
            remove.disabled = card.content.length <= 1;
            row.append(remove); points.append(row);
          });
        }
        const add = button('+ 添加要点', 'plain-button', () => {
          if (card.content.length >= 5) return;
          card.content.push(''); changed(); drawPoints(); add.disabled = card.content.length >= 5;
          points.lastElementChild.querySelector('textarea').focus();
        });
        add.disabled = card.content.length >= 5;
        drawPoints(); copy.append(add);
      }
      const imageKey = index ? 'image' : 'cover_image';
      const imageEditor = node('details', 'image-editor');
      imageEditor.tabIndex = 0; imageEditor.setAttribute('aria-label', (index ? '内容页 ' + index : '封面') + '配图区域，可上传、拖放或粘贴图片');
      const imageSummary = node('summary', 'image-summary');
      if (card[imageKey]) {
        const img = node('img'); img.src = card[imageKey]; img.alt = '当前配图'; imageSummary.append(img);
      }
      imageSummary.append(node('span', '', card[imageKey] ? '替换配图' : '+ 添加配图'));
      imageEditor.append(imageSummary);
      const fileLabel = node('label', '', '配图（可选）');
      const input = node('input'); input.type = 'file'; input.accept = 'image/png,image/jpeg,image/webp';
      fileLabel.append(input); imageEditor.append(fileLabel);
      const help = node('p', 'field-help', 'PNG / JPEG / WebP · ≤2 MiB，可拖放或粘贴。');
      imageEditor.append(help);
      if (card[imageKey]) {
        imageEditor.append(button('移除配图', 'plain-button', () => { card[imageKey] = null; changed(); showEditor(); }));
      }
      input.addEventListener('change', () => uploadImage(input.files[0], index));
      imageEditor.addEventListener('focusin', () => { lastImageEditor = index; });
      imageEditor.addEventListener('dragover', e => { e.preventDefault(); imageEditor.classList.add('dragging'); });
      imageEditor.addEventListener('dragleave', () => imageEditor.classList.remove('dragging'));
      imageEditor.addEventListener('drop', e => { e.preventDefault(); imageEditor.classList.remove('dragging'); uploadImage(e.dataTransfer.files[0], index); });
      article.append(imageEditor); $('editor').append(article);
    });
  }
  function validSlides() {
    if (!slides) return false;
    if (slides.slides.length > 7) { status('最多生成 8 张卡片（含封面）。', 'error'); return false; }
    if (!slides.cover_title.trim() || slides.cover_tags.length > 5 || slides.cover_tags.some(tag => tag.length > 10) ||
        slides.slides.some(card => !card.title.trim() || !card.content.length || card.content.some(point => !point.trim()))) {
      status('请补全标题和要点；标签最多 5 个，每个最多 10 字。', 'error'); return false;
    }
    return true;
  }
  function regenerateCard(index) {
    if (!validSlides()) return;
    const settings = config(); if (!settings) return;
    const body = {slides_data: slides, slide_index: index, config: settings, style: style.value};
    task('正在重新整理这一页；期间修改内容后将忽略旧响应。',
      signal => requestJSON('/regenerate-slide', body, signal), result => {
        slides = result.slides_data; changed(); showEditor(); status('这一页已更新，原有配图已保留。');
      });
  }
  function uploadImage(file, index) {
    if (!file || pending) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      status('请选择不超过 2 MiB 的 PNG、JPEG 或 WebP 位图。', 'error'); return;
    }
    task('正在验证配图……', async signal => {
      const body = new FormData(); body.append('file', file);
      const response = await fetch('/upload-image', {method: 'POST', body, signal});
      const result = await response.json(); if (!response.ok) throw new Error(result.error || '配图处理失败。'); return result;
    }, result => {
      const card = index ? slides.slides[index - 1] : slides;
      card[index ? 'image' : 'cover_image'] = result.image_data; changed(); showEditor(); status('配图已验证，渲染时会按模板裁切。');
    });
  }
  document.addEventListener('paste', e => {
    const file = [...(e.clipboardData?.items || [])].find(item => item.kind === 'file' && item.type.startsWith('image/'))?.getAsFile();
    const target = document.activeElement?.closest('.image-editor');
    if (file && slides && target && lastImageEditor !== null) { e.preventDefault(); uploadImage(file, lastImageEditor); }
  });
  async function render() {
    if (pending || !validSlides()) return;
    const body = {slides_data: slides, style: style.value};
    $('card-stage').classList.add('is-rendering');
    $('card-stage').setAttribute('aria-busy', 'true');
    try {
      await task('正在为卡片施加样式……', signal => requestJSON('/render', body, signal), result => {
        images = result.images; showResults(); status('图卡已就绪，可以单张下载或整组打包。');
      });
    } finally {
      $('card-stage').classList.remove('is-rendering');
      $('card-stage').setAttribute('aria-busy', 'false');
    }
  }
  $('render').addEventListener('click', render);
  function showResults() {
    $('editor').hidden = true;
    $('edit-cards').hidden = false; $('edit-cards').textContent = '编辑文案';
    $('download-all').hidden = false;
    $('render').textContent = '⑤ 重新生成图卡';
    $('results-section').hidden = false; $('results').replaceChildren();
    images.forEach((image, index) => {
      const article = node('article', 'result-card');
      article.style.setProperty('--card-order', index);
      const enlarge = button('', 'sample-button', () => Tuka.showImages('图卡 ' + (index + 1), [image.data]));
      enlarge.setAttribute('aria-label', '放大图卡 ' + (index + 1));
      const img = node('img'); img.src = image.data; img.alt = '生成图卡 ' + (index + 1); img.width = 1242; img.height = 1660;
      enlarge.append(img); article.append(enlarge);
      const link = node('a', '', '下载第 ' + String(index + 1).padStart(2, '0') + ' 张 PNG');
      link.href = image.data; link.download = image.filename;
      link.addEventListener('click', () => Tuka.event('download_click', style.value));
      article.append(link); $('results').append(article);
    });
  }
  $('edit-cards').addEventListener('click', () => {
    const editing = $('editor').hidden;
    $('editor').hidden = !editing;
    $('results-section').hidden = editing;
    $('edit-cards').textContent = editing ? '查看成品' : '编辑文案';
  });
  $('download-all').addEventListener('click', () => {
    if (!images.length || pending) return;
    Tuka.event('download_click', style.value);
    const body = {images: images.map(image => image.data)};
    task('正在打包当前图卡……', async signal => {
      const response = await fetch('/download-all', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal});
      if (!response.ok) { const result = await response.json(); throw new Error(result.error || '打包失败。'); }
      return response.blob();
    }, blob => {
      const url = URL.createObjectURL(blob); const link = node('a'); link.href = url; link.download = 'tuka-cards.zip';
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
      status('已发起 ZIP 下载，请在浏览器中确认保存。');
    });
  });
})();
