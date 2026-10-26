'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const content = $('content');
  const style = $('style-select');
  let slides = null;
  let images = [];
  const renderCache = new Map();
  let renderedStyle = null;
  let queuedStyleRender = false;
  let revision = 0;
  let pending = null;
  let lastImageEditor = null;
  let modelRequest = null;
  let modelsLoaded = false;
  const PROVIDER_URLS = {
    deepseek: 'https://platform.deepseek.com/api_keys',
    minimax: 'https://platform.minimax.cn/user-center/basic-information/interface-key',
    kimi: 'https://platform.moonshot.cn/console/api-keys',
    zhipu: 'https://open.bigmodel.cn/usercenter/apikeys',
    doubao: 'https://ark.volcengine.com/region:cn-beijing/apikey',
    qwen: 'https://bailian.console.aliyun.com/?apiKey=1#/api-key',
    qianfan: 'https://console.bce.baidu.com/iam/#/iam/apikey/list',
    hunyuan: 'https://console.cloud.tencent.com/tokenhub/apikey'
  };
  const PRESET_MODELS = {
    minimax: ['MiniMax-M3', 'MiniMax-M3.1-Flash'],
    zhipu: ['glm-4.7-flash', 'glm-5.3', 'glm-5.3-flash', 'glm-5.3-flashx', 'glm-5.2', 'glm-4.5-flash'],
    doubao: ['doubao-seed-2-0-mini-260428', 'doubao-seed-2-1-lite-260915', 'doubao-seed-2-1-pro-260915', 'doubao-seed-2-1-turbo-260628'],
    qwen: ['qwen-plus', 'qwen3.8-flash', 'qwen3.8-max', 'qwen3.7-plus']
  };
  function updateProviderLink() {
    const link = $('provider-link');
    if (link) {
      const p = $('provider').value;
      link.href = PROVIDER_URLS[p] || 'https://platform.deepseek.com/api_keys';
    }
  }
  let draftTimer = null;
  const DRAFT_KEY = 'tuka_local_draft';
  const validDraftImage = image => image === null || (typeof image === 'string' && image.length <= 3_000_000 && image.startsWith('data:image/png;base64,'));
  function validDraftSlides(value) {
    return value && typeof value === 'object' && typeof value.cover_title === 'string' && value.cover_title.length <= 20000 &&
      typeof value.cover_subtitle === 'string' && value.cover_subtitle.length <= 20000 &&
      Array.isArray(value.cover_tags) && value.cover_tags.length <= 5 && value.cover_tags.every(tag => typeof tag === 'string' && tag.length <= 20000) &&
      validDraftImage(value.cover_image) && Array.isArray(value.slides) && value.slides.length >= 1 && value.slides.length <= 7 && value.slides.every(card =>
        card && typeof card.title === 'string' && card.title.length <= 20000 && Array.isArray(card.content) && card.content.length >= 1 && card.content.length <= 5 &&
        card.content.every(point => typeof point === 'string' && point.length <= 20000) && validDraftImage(card.image));
  }
  function readLocalDraft() {
    try {
      const draft = JSON.parse(localStorage.getItem(DRAFT_KEY));
      if (draft && typeof draft.content === 'string' && draft.content.length <= 20000 && (draft.slides === null || validDraftSlides(draft.slides))) return draft;
    } catch (_) {}
    try {
      const savedContent = localStorage.getItem('tuka_local_content') || '';
      const savedSlides = localStorage.getItem('tuka_local_slides');
      const parsedSlides = savedSlides ? JSON.parse(savedSlides) : null;
      return {content: savedContent.slice(0, 20000), slides: validDraftSlides(parsedSlides) ? parsedSlides : null};
    } catch (_) { return null; }
  }
  function persistLocalDraft() {
    try {
      if (content.value.trim() || slides) localStorage.setItem(DRAFT_KEY, JSON.stringify({content: content.value, slides}));
      else localStorage.removeItem(DRAFT_KEY);
      localStorage.removeItem('tuka_local_content');
      localStorage.removeItem('tuka_local_slides');
    } catch (_) { status('本地存储空间不足，最新草稿未能保存；请先复制正文。', 'error'); }
  }
  function saveLocalDraft() {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(persistLocalDraft, 600);
  }
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
    renderCache.clear();
    queuedStyleRender = false;
    revision++;
    saveLocalDraft();
    if (images.length) {
      images = [];
      $('results').replaceChildren();
      $('results-section').hidden = true;
      $('editor').hidden = false;
      $('download-all').hidden = true;
      $('edit-cards').hidden = true;
      $('output-title').textContent = '文案草稿';
      $('render').innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> 渲染图卡';
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
  function checkPresetModels(key) {
    const p = $('provider').value;
    const presets = PRESET_MODELS[p];
    if (presets && presets.length && key) {
      $('model').replaceChildren(new Option('请选择一个模型', ''), ...presets.map(id => new Option(id, id)));
      $('model').value = presets[0];
      $('model').size = 1;
      $('model').disabled = false;
      modelsLoaded = true;
      $('model-selection').textContent = `已就绪：${presets[0]}`;
      $('model-status').textContent = '已自动选用官方推荐模型，可直接开始。';
      fieldError($('model'), 'model-error', '');
      return true;
    }
    return false;
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
    const key = $('api-key').value.trim();
    if (key && checkPresetModels(key)) return;
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
  async function task(label, action, apply, kind = '') {
    if (pending) return;
    const controller = new AbortController();
    const current = {controller, revision, kind};
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
      return true;
    } catch (error) {
      if (pending === current) {
        status(error.name === 'AbortError' ? '操作已取消或超时，当前内容已保留。' : error.message, 'error');
      }
    } finally {
      clearTimeout(timer);
      if (pending === current) {
        pending = null; busy(false);
        if (queuedStyleRender) { queuedStyleRender = false; render(true); }
      }
    }
  }
  $('cancel-task').addEventListener('click', () => {
    if (images.length && (pending?.kind === 'render' || queuedStyleRender)) { style.value = renderedStyle; markStyleSelection(); }
    queuedStyleRender = false;
    if (pending) pending.controller.abort();
  });
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
    updateProviderLink();
    resetModels();
  });
  $('api-key').addEventListener('input', () => {
    revision++;
    const key = $('api-key').value.trim();
    if (!checkPresetModels(key)) {
      resetModels();
    }
    fieldError($('api-key'), 'key-error', '');
  });
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
  const EXAMPLES = [
    {
      name: '建立可持续的创作习惯（随笔心得）',
      text: '给灵感留白：建立一个可持续的创作习惯\n\n灵感并不总在你坐到书桌前出现。把每天看到的细节、读到的句子和突然冒出的想法记在同一个地方，不急着判断价值。每天留出十五分钟，选一个问题，写下你真实的观察。\n\n初稿先求完整，再求漂亮。一次只打磨一个核心观点，用具体的故事和可核对的数据支撑它。删掉没有信息量的形容词，把长句拆短，给读者留出理解的空间。\n\n写完后大声读一遍，再检查事实和来源。把内容整理成清楚的标题、几个要点和一个行动建议。定期回看自己的素材，看看哪些话题值得继续。慢一点，持续地做，表达就会逐渐长出自己的样子。'
    },
    {
      name: '个人深度复盘（知识干货）',
      text: '如何把一门核心技能学到前20%？\n\n一、最小闭环，拒绝虚假勤奋\n很多人学习总是停留在收藏课程和买书，从不动手。真正的高手会在第一周就做出一个哪怕粗糙的最小成品。用产出倒逼输入，遇到卡点再定向补齐知识。\n\n二、建立高频外部反馈机制\n关在房间里自嗨学不会真本事。把半成品发给同行或公开发布，哪怕只有两条批评，也能迅速帮你校准盲区。在真实的阻力与互动中快速迭代认知。\n\n三、框架化与底层模型迁移\n不要孤立记忆散乱知识点。把解决一个具体问题的步骤沉淀为清单或卡片。每当你掌握一个底层逻辑，就能用它去解释和解决更多领域的复杂问题。'
    }
  ];
  let exampleIndex = 0;
  $('use-example').addEventListener('click', () => {
    const item = EXAMPLES[exampleIndex % EXAMPLES.length];
    exampleIndex++;
    content.value = item.text;
    invalidateInput(); validateContent(); content.focus();
    status(`已填入示例：《${item.name}》`);
    saveLocalDraft();
  });
  $('generate').addEventListener('click', () => {
    const validContent = validateContent();
    const settings = config();
    if (!validContent || !settings) { if (!validContent && settings) content.focus(); return; }
    $('model-config').open = false;
    const body = {content: content.value, config: settings, style: style.value};
    task('正在整理文案，通常需要几秒……',
      signal => requestJSON('/preview', body, signal), result => {
        slides = result.slides_data;
        changed();
        showEditor();
        let message = '文案已整理。请检查各卡片标题和要点，确认后点击下方“渲染图卡”。';
        if (result.draft_issues?.length) message = '草稿已保留，部分文字仍超长；请修改标记字段后渲染。\n' + result.draft_issues.join('；');
        const selection = result.image_summary;
        if (selection?.candidates) {
          message += `\n已根据图片说明和上下文，从 ${selection.candidates} 张候选配图中采用 ${selection.used} 张，其余未使用。`;
          if (selection.failed) message += `其中 ${selection.failed} 张选中图片无法安全获取，已跳过，可在编辑区补图。`;
        }
        status(message);
      });
  });
  function markStyleSelection() {
    document.querySelectorAll('input[name="style-choice"]').forEach(option => {
      option.checked = option.value === style.value;
      option.closest('.style-option').classList.toggle('is-selected', option.checked);
    });
  }
  style.addEventListener('change', () => {
    revision++;
    markStyleSelection();
    Tuka.event('template_select', style.value);
    if (pending && (pending.kind === 'render' || images.length)) {
      queuedStyleRender = true;
      $('card-stage').classList.remove('is-rendering');
    } else if (images.length && !pending) {
      render(true);
    }
  });
  document.querySelectorAll('input[name="style-choice"]').forEach(option => option.addEventListener('change', () => {
    if (!option.checked) return;
    style.value = option.value;
    style.dispatchEvent(new Event('change', {bubbles: true}));
  }));
  function placeStylePreview(option) {
    const image = option.querySelector('.style-preview img');
    if (!image.hasAttribute('src')) image.src = image.dataset.src;
    const rect = option.getBoundingClientRect();
    const width = Math.min(190, window.innerWidth - 32);
    const height = width * (1660 / 1242) + 42;
    const rightSpace = window.innerWidth - rect.right;
    const left = rightSpace > width + 16 ? rect.right + 8 : rect.left > width + 16 ? rect.left - width - 8 : Math.max(16, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 16));
    const top = Math.max(16, Math.min(rect.top + rect.height / 2 - height / 2, window.innerHeight - height - 16));
    option.style.setProperty('--preview-left', left + 'px');
    option.style.setProperty('--preview-top', top + 'px');
  }
  let stylePreviewTimer = null;
  let stylePreviewOption = null;
  function hideStylePreview() {
    clearTimeout(stylePreviewTimer);
    stylePreviewOption?.classList.remove('is-previewing');
    stylePreviewOption = null;
  }
  document.querySelectorAll('.style-option').forEach(option => {
    option.addEventListener('pointerenter', event => {
      if (event.pointerType !== 'mouse') return;
      hideStylePreview();
      stylePreviewOption = option;
      stylePreviewTimer = setTimeout(() => {
        if (stylePreviewOption !== option || !option.matches(':hover')) return;
        placeStylePreview(option);
        option.classList.add('is-previewing');
      }, 1000);
    });
    option.addEventListener('pointerleave', () => { if (stylePreviewOption === option) hideStylePreview(); });
    option.addEventListener('pointerdown', hideStylePreview);
    option.addEventListener('click', hideStylePreview);
  });
  $('style-gallery').addEventListener('toggle', () => { if (!$('style-gallery').open) hideStylePreview(); });
  window.addEventListener('blur', hideStylePreview);
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
    input.value = value; input.placeholder = labelText.split(' · ')[0];
    const overflow = node('span', 'field-help');
    function checkLength() {
      const length = [...input.value].length;
      const invalid = length > max;
      input.setAttribute('aria-invalid', String(invalid));
      input.setCustomValidity(invalid ? `当前 ${length} 字，最多 ${max} 字，请缩短。` : '');
      overflow.textContent = invalid ? `当前 ${length} 字，最多 ${max} 字，请缩短。` : '';
      overflow.hidden = !invalid;
    }
    checkLength();
    input.addEventListener('input', () => { checkLength(); apply(input.value); changed(); });
    label.append(overflow);
    label.append(caption, input); parent.append(label); return input;
  }
  function showEditor() {
    $('empty-state').hidden = true;
    $('editor').hidden = false;
    $('results-section').hidden = true;
    $('results-hint').hidden = true;
    $('edit-cards').hidden = true;
    $('download-all').hidden = true;
    $('output-title').textContent = '文案草稿';
    $('render').innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> 渲染图卡';
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
    const invalidField = $('editor').querySelector('[aria-invalid="true"]');
    if (invalidField) { status('请先缩短标记为超长的文字，再渲染图卡。', 'error'); invalidField.focus(); return false; }
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
  async function render(switchStyle = false) {
    if (pending || !validSlides()) return;
    const requestedStyle = style.value;
    if (switchStyle && renderCache.has(requestedStyle)) {
      images = renderCache.get(requestedStyle);
      renderCache.delete(requestedStyle); renderCache.set(requestedStyle, images);
      renderedStyle = requestedStyle;
      showResults(false); status('图卡已渲染完成，已立即应用缓存样式；文案与配图保持不变。');
      return;
    }
    const body = {slides_data: slides, style: requestedStyle};
    if (!switchStyle) $('card-stage').classList.add('is-rendering');
    $('card-stage').setAttribute('aria-busy', 'true');
    try {
      const applied = await task(switchStyle ? '正在应用新样式，仅重新排版图片，不调用大模型……' : '正在渲染图卡（预计耗时 5~10 秒）……',
        signal => requestJSON('/render', body, signal), result => {
          images = result.images; renderedStyle = requestedStyle;
          renderCache.delete(requestedStyle); renderCache.set(requestedStyle, images);
          // Keep at most two styles and 24 MiB of image data in this page only.
          while (renderCache.size > 2 || [...renderCache.values()].reduce((total, cards) => total + cards.reduce((size, card) => size + card.data.length, 0), 0) > 24 * 1024 * 1024) {
            renderCache.delete(renderCache.keys().next().value);
          }
          showResults(!switchStyle); status('图卡已渲染完成，可点击卡片放大查看，或直接整组下载 ZIP。');
        }, 'render');
      if (!applied && !pending && switchStyle && images.length && style.value === requestedStyle) {
        style.value = renderedStyle; markStyleSelection();
      }
    } finally {
      $('card-stage').classList.remove('is-rendering');
      if (pending?.kind !== 'render') $('card-stage').setAttribute('aria-busy', 'false');
    }
  }
  $('render').addEventListener('click', () => render());
  function showResults(animate = true) {
    $('editor').hidden = true;
    $('edit-cards').hidden = false;
    $('edit-cards').innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> 编辑文案';
    $('download-all').hidden = false;
    $('output-title').textContent = '图卡预览';
    $('results-hint').hidden = false;
    $('render').innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> 重新渲染图卡';
    $('results-section').hidden = false; $('results').replaceChildren();
    images.forEach((image, index) => {
      const article = node('article', 'result-card');
      if (!animate) article.style.animation = 'none';
      article.style.setProperty('--card-order', index);
      const enlarge = button('', 'sample-button', () => Tuka.showImages('图卡预览', images.map(card => card.data), index));
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
    $('results-hint').hidden = editing;
    $('output-title').textContent = editing ? '文案草稿' : '图卡预览';
    $('edit-cards').innerHTML = editing
      ? '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><path d="M21 15l-5-5L5 21"/></svg> 查看成品'
      : '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> 编辑文案';
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
  function checkLocalDraft() {
    const draft = readLocalDraft();
    if (draft && (draft.content.trim() || draft.slides) && !content.value.trim()) $('draft-notice').hidden = false;
  }
  const restoreBtn = $('restore-draft');
  if (restoreBtn) {
    restoreBtn.addEventListener('click', () => {
      const draft = readLocalDraft();
      if (draft) {
        try {
          content.value = draft.content;
          invalidateInput(); validateContent();
          if (draft.slides) {
            slides = draft.slides;
            changed();
            showEditor();
          }
        $('draft-notice').hidden = true;
        status('已恢复本地草稿。');
        } catch (_) { status('草稿无法完整恢复，请检查正文后继续。', 'error'); }
      }
    });
  }
  const discardBtn = $('discard-draft');
  if (discardBtn) {
    discardBtn.addEventListener('click', () => {
      clearTimeout(draftTimer);
      try {
        localStorage.removeItem(DRAFT_KEY);
        localStorage.removeItem('tuka_local_content');
        localStorage.removeItem('tuka_local_slides');
        $('draft-notice').hidden = true;
        status('已清除本地暂存草稿。');
      } catch (_) {}
    });
  }
  window.addEventListener('beforeunload', event => {
    if (draftTimer) { clearTimeout(draftTimer); draftTimer = null; persistLocalDraft(); }
    if (content.value.trim().length >= 50 || slides) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  updateProviderLink();
  checkLocalDraft();
})();
