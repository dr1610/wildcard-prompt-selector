(function () {
  "use strict";

  const state = {
    category: "",
    tag: "",
    image: "all",
    query: "",
    searchMode: "and",
  };

  function q(selector, root = document) {
    return root.querySelector(selector);
  }

  function qa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function wildcardPromptSelectorPages() {
    return qa("[id$='_wildcard_prompt_selector']").filter((page) => q(".vw-extra-card", page));
  }

  function pageCards(page) {
    return qa(".vw-extra-card", page);
  }

  function cardTitle(card) {
    const title = q(".name", card);
    return title ? title.textContent.trim() : card.dataset.name || "Wildcard Prompt Selector";
  }

  function cardDescription(card) {
    const desc = q(".description", card);
    return desc ? desc.textContent.trim() : "";
  }

  function cardImage(card) {
    const image = q("img.preview", card);
    return image ? image.src : "";
  }

  function uniqueSorted(values) {
    return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function parseTokens(query) {
    const tokens = [];
    const re = /"([^"]+)"|(\S+)/g;
    let match;
    while ((match = re.exec(query || ""))) {
      tokens.push(String(match[1] || match[2] || "").toLowerCase().replace(/^#/, ""));
    }
    return tokens.filter(Boolean);
  }

  function cardSearchBlob(card) {
    return [
      card.textContent || "",
      card.dataset.vwCategory || "",
      card.dataset.vwSource || "",
      card.dataset.vwTags || "",
      card.dataset.vwLine || "",
    ].join(" ").toLowerCase();
  }

  function wildcardPromptSelectorTreeClickGuard(event) {
    const content = event.target.closest(".vw-source-tree .tree-list-content-dir, .vw-source-tree .tree-list-content-file");
    if (!content) return;
    const page = content.closest("[id$='_wildcard_prompt_selector']");
    if (!page) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const item = content.closest(".tree-list-item");
    const childList = item ? item.querySelector(":scope > ul.tree-list--subgroup") : null;
    if (childList) {
      childList.hidden = !childList.hidden;
      content.classList.toggle("tree-list-content-dir-open", !childList.hidden);
    }

    const tabMatch = page.id.match(/^(txt2img|img2img)_wildcard_prompt_selector$/);
    const tabname = tabMatch ? tabMatch[1] : "";
    const search = tabname ? document.getElementById(`${tabname}_wildcard_prompt_selector_extra_search`) : null;
    if (search) {
      search.value = content.dataset.path || "";
      search.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function buildToolbar(page) {
    if (page.dataset.vwToolbarBound === "1") return;
    page.dataset.vwToolbarBound = "1";
    const cards = pageCards(page);
    const categories = uniqueSorted(cards.map((card) => card.dataset.vwCategory || ""));
    const tags = uniqueSorted(
      cards.flatMap((card) =>
        (card.dataset.vwTags || "")
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean)
      )
    );

    const toolbar = document.createElement("div");
    toolbar.className = "vw-extra-toolbar";
    toolbar.innerHTML = `
      <div class="vw-filter-row">
        <input class="vw-local-search" type="search" placeholder="Wildcard Prompt Selector search">
        <select class="vw-search-mode" title="Search mode">
          <option value="and">AND</option>
          <option value="or">OR</option>
        </select>
        <details class="vw-category-tree">
          <summary>Category</summary>
          <div class="vw-category-list"></div>
        </details>
        <select class="vw-image-select" title="Image filter">
          <option value="all">All images</option>
          <option value="with">Image only</option>
          <option value="without">No image</option>
        </select>
        <button type="button" class="vw-clear-filter">Clear</button>
      </div>
      <div class="vw-active-filter"></div>
      <div class="vw-tag-list"></div>
    `;

    const categoryList = q(".vw-category-list", toolbar);
    const allButton = document.createElement("button");
    allButton.type = "button";
    allButton.textContent = "All";
    allButton.dataset.category = "";
    categoryList.appendChild(allButton);
    for (const category of categories) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = category;
      button.dataset.category = category;
      button.style.paddingLeft = `${Math.min(category.split("/").length - 1, 5) * 14 + 8}px`;
      categoryList.appendChild(button);
    }

    const tagList = q(".vw-tag-list", toolbar);
    for (const tag of tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `#${tag}`;
      button.dataset.tag = tag;
      tagList.appendChild(button);
    }

    toolbar.addEventListener("click", (event) => {
      const categoryButton = event.target.closest("[data-category]");
      const tagButton = event.target.closest("[data-tag]");
      if (categoryButton) {
        state.category = categoryButton.dataset.category || "";
        applyFilters();
      }
      if (tagButton) {
        state.tag = tagButton.dataset.tag || "";
        applyFilters();
      }
      if (event.target.closest(".vw-clear-filter")) {
        state.category = "";
        state.tag = "";
        state.image = "all";
        state.query = "";
        state.searchMode = "and";
        const imageSelect = q(".vw-image-select", toolbar);
        const search = q(".vw-local-search", toolbar);
        const mode = q(".vw-search-mode", toolbar);
        if (imageSelect) imageSelect.value = "all";
        if (search) search.value = "";
        if (mode) mode.value = "and";
        applyFilters();
      }
    });

    const search = q(".vw-local-search", toolbar);
    search.addEventListener("input", () => {
      state.query = search.value;
      applyFilters();
    });
    const searchMode = q(".vw-search-mode", toolbar);
    searchMode.addEventListener("change", () => {
      state.searchMode = searchMode.value;
      applyFilters();
    });
    const imageSelect = q(".vw-image-select", toolbar);
    imageSelect.addEventListener("change", () => {
      state.image = imageSelect.value;
      applyFilters();
    });

    page.prepend(toolbar);
    applyFilters();
  }

  function applyFilters() {
    for (const page of wildcardPromptSelectorPages()) {
      let visible = 0;
      const cards = pageCards(page);
      const tokens = parseTokens(state.query);
      for (const card of cards) {
        const category = card.dataset.vwCategory || "";
        const tags = (card.dataset.vwTags || "").split(",").map((tag) => tag.trim());
        const hasImage = card.dataset.vwHasImage === "1";
        const blob = cardSearchBlob(card);
        const categoryMatch = !state.category || category === state.category || category.startsWith(`${state.category}/`);
        const tagMatch = !state.tag || tags.includes(state.tag);
        const imageMatch =
          state.image === "all" ||
          (state.image === "with" && hasImage) ||
          (state.image === "without" && !hasImage);
        const searchMatch =
          tokens.length === 0 ||
          (state.searchMode === "or"
            ? tokens.some((token) => blob.includes(token))
            : tokens.every((token) => blob.includes(token)));
        const show = categoryMatch && tagMatch && imageMatch && searchMatch;
        card.classList.toggle("vw-filter-hidden", !show);
        if (show) visible += 1;
      }
      const active = q(".vw-active-filter", page);
      if (active) {
        const labels = [];
        if (state.category) labels.push(`Category: ${state.category}`);
        if (state.tag) labels.push(`#${state.tag}`);
        if (state.image !== "all") labels.push(state.image === "with" ? "Image only" : "No image");
        if (state.query) labels.push(`${state.searchMode.toUpperCase()}: ${state.query}`);
        active.textContent = `${visible} / ${cards.length} visible${labels.length ? " - " + labels.join(" / ") : ""}`;
      }
    }
  }

  function ensureModal() {
    let modal = q("#vw-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "vw-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="vw-modal-backdrop"></div>
      <div class="vw-modal-panel">
        <div class="vw-modal-head">
          <strong class="vw-modal-title">Wildcard Prompt Selector</strong>
          <button type="button" class="vw-modal-close">Close</button>
        </div>
        <div class="vw-modal-body"></div>
      </div>
    `;
    modal.addEventListener("click", (event) => {
      if (event.target.closest(".vw-modal-close") || event.target.classList.contains("vw-modal-backdrop")) {
        closeModal();
      }
    });
    document.body.appendChild(modal);
    return modal;
  }

  function openModal(title, body) {
    const modal = ensureModal();
    q(".vw-modal-title", modal).textContent = title;
    const modalBody = q(".vw-modal-body", modal);
    modalBody.innerHTML = "";
    modalBody.appendChild(body);
    modal.hidden = false;
  }

  function closeModal() {
    const modal = q("#vw-modal");
    if (modal) modal.hidden = true;
  }

  async function getItem(id) {
    const response = await fetch(`/wildcard-prompt-selector/item?id=${encodeURIComponent(id)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to load item");
    return data.item;
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      if (!file) {
        resolve("");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
      reader.readAsDataURL(file);
    });
  }

  async function saveItem(payload) {
    const response = await fetch("/wildcard-prompt-selector/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to save item");
    return data;
  }

  function refreshWildcardPromptSelectorPages() {
    for (const page of wildcardPromptSelectorPages()) {
      const button = document.getElementById(`${page.id}_extra_refresh_internal`);
      if (button) button.click();
    }
  }

  async function openEdit(card) {
    const id = card.dataset.vwId;
    const item = await getItem(id);
    const form = document.createElement("form");
    form.className = "vw-edit-form";
    form.innerHTML = `
      <label>表示名の上書き<input name="display_name_override"></label>
      <label>Wildcard候補<textarea name="prompt" readonly></textarea></label>
      <label>Source<input name="source" readonly></label>
      <label>Line<input name="line" readonly></label>
      <label>クリック時に前へ追加するプロンプト<textarea name="prepend_prompt"></textarea></label>
      <label>クリック時に後ろへ追加するプロンプト<textarea name="append_prompt"></textarea></label>
      <label>Negative promptへ追加<textarea name="append_negative"></textarea></label>
      <label>Tags<input name="tags" placeholder="夏, 海, 水着"></label>
      <label>Memo<textarea name="memo"></textarea></label>
      <label>参考画像<input name="image" type="file" accept="image/png,image/jpeg,image/webp"></label>
      <label class="vw-inline"><input name="clear_image" type="checkbox"> 現在の参考画像リンクを外す</label>
      <div class="vw-current-image"></div>
      <div class="vw-form-actions">
        <button type="submit">保存</button>
        <button type="button" class="vw-modal-close">取消</button>
      </div>
      <div class="vw-form-status"></div>
    `;
    form.elements.display_name_override.value = item.display_name_override || "";
    form.elements.prompt.value = item.prompt || "";
    form.elements.source.value = item.source_file || "";
    form.elements.line.value = item.line_number || "";
    form.elements.prepend_prompt.value = item.prepend_prompt || "";
    form.elements.append_prompt.value = item.append_prompt || "";
    form.elements.append_negative.value = item.append_negative || "";
    form.elements.tags.value = Array.isArray(item.tags) ? item.tags.join(", ") : "";
    form.elements.memo.value = item.memo || "";
    const imageBox = q(".vw-current-image", form);
    const imageSrc = cardImage(card);
    imageBox.innerHTML = imageSrc ? `<img src="${imageSrc}" alt=""><span>${escapeHtml(item.image || "")}</span>` : "<span>参考画像なし</span>";

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const status = q(".vw-form-status", form);
      status.textContent = "保存中...";
      try {
        const file = form.elements.image.files[0];
        const imageDataUrl = await readFileAsDataUrl(file);
        await saveItem({
          id,
          display_name_override: form.elements.display_name_override.value,
          prepend_prompt: form.elements.prepend_prompt.value,
          append_prompt: form.elements.append_prompt.value,
          append_negative: form.elements.append_negative.value,
          tags: form.elements.tags.value,
          memo: form.elements.memo.value,
          clear_image: form.elements.clear_image.checked,
          image_data_url: imageDataUrl,
          image_name: file ? file.name : "",
        });
        status.textContent = "保存しました。カードを更新中...";
        refreshWildcardPromptSelectorPages();
        setTimeout(closeModal, 600);
      } catch (error) {
        status.textContent = error.message || String(error);
      }
    });
    openModal(`Wildcard Prompt Selector編集: ${cardTitle(card)}`, form);
  }

  function openPreview(card) {
    const body = document.createElement("div");
    body.className = "vw-preview-modal";
    const imageSrc = cardImage(card);
    body.innerHTML = `
      <div class="vw-large-image">${imageSrc ? `<img src="${imageSrc}" alt="">` : "<div>No Image</div>"}</div>
      <h3>${escapeHtml(cardTitle(card))}</h3>
      <p>${escapeHtml(card.dataset.vwCategory || "Root")}</p>
      <p>${escapeHtml(card.dataset.vwSource || "")}: line ${escapeHtml(card.dataset.vwLine || "")}</p>
      <pre></pre>
    `;
    q("pre", body).textContent = cardDescription(card);
    openModal(cardTitle(card), body);
  }

  function bindCards() {
    for (const page of wildcardPromptSelectorPages()) {
      buildToolbar(page);
    }
    for (const card of qa(".vw-extra-card")) {
      if (card.dataset.vwBound === "1") continue;
      card.dataset.vwBound = "1";
      const edit = q(".vw-edit-button", card);
      const preview = q(".vw-preview-button", card);
      if (edit) {
        edit.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          openEdit(card).catch((error) => alert(error.message || String(error)));
        });
      }
      if (preview) {
        preview.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          openPreview(card);
        });
      }
    }
    applyFilters();
  }

  document.addEventListener("DOMContentLoaded", bindCards);
  document.addEventListener("gradio:loaded", bindCards);
  document.addEventListener("gradio:render", bindCards);
  document.addEventListener("click", wildcardPromptSelectorTreeClickGuard, true);
  setInterval(bindCards, 1500);
})();


