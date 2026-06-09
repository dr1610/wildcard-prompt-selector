from __future__ import annotations

import base64
import hashlib
import html
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import Request
from fastapi.responses import JSONResponse

from modules import script_callbacks, shared, ui_extra_networks
from modules.ui_extra_networks import quote_js
import modules.scripts as scripts
from modules.scripts import basedir


EXTENSION_NAME = "wildcard_prompt_selector"
BASE_DIR = Path(basedir())
CONFIG_PATH = BASE_DIR / "config.json"
METADATA_PATH = BASE_DIR / "wildcard_prompt_selector_metadata.json"
PREVIEWS_DIR = BASE_DIR / "previews"
CUSTOM_PREVIEWS_DIR = PREVIEWS_DIR / "custom"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MAPPING_NAMES = ("image_mapping.json",)

DEFAULT_CONFIG = {
    "wildcard_paths": [
        "sample_wildcards"
    ],
    "append_separator": ", ",
    "default_insert_target": "prompt",
    "extra_networks_tab_name": "Wildcard Prompt Selector",
    "enable_extra_networks_integration": True,
    "enable_fallback_panel": False,
    "enable_txt2img": True,
    "enable_img2img": True,
    "enable_category_tree": True,
    "enable_tag_filter": True,
    "enable_image_preview": True,
    "enable_multi_select": False,
    "avoid_duplicate_insert": True,
    "thumbnail_size": 160,
    "auto_insert_negative": False,
    "max_cards": 20000,
}


def log(message: str) -> None:
    print(f"[wildcard_prompt_selector] {message}")


def detect_wildcard_paths() -> list[str]:
    candidates = [
        BASE_DIR.parent / "sd-dynamic-prompts" / "wildcards",
        BASE_DIR.parent / "stable-diffusion-webui-wildcards" / "wildcards",
        BASE_DIR.parent / "wildcards",
    ]
    return [path.as_posix() for path in candidates if path.exists()]


def is_sample_wildcard_config(paths: Any) -> bool:
    return isinstance(paths, list) and len(paths) == 1 and str(paths[0]).replace("\\", "/") == "sample_wildcards"

def ensure_files() -> None:
    try:
        PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            config = dict(DEFAULT_CONFIG)
            detected = detect_wildcard_paths()
            if detected:
                config["wildcard_paths"] = detected
            CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        if not METADATA_PATH.exists():
            METADATA_PATH.write_text("{}", encoding="utf-8")
    except Exception as exc:
        log(f"startup file generation failed: {exc}")


def load_json(path: Path, fallback: Any) -> Any:
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"failed to load {path.name}: {exc}")
        return fallback


def load_config() -> dict[str, Any]:
    ensure_files()
    config = dict(DEFAULT_CONFIG)
    loaded = load_json(CONFIG_PATH, {})
    if isinstance(loaded, dict):
        config.update(loaded)
    detected = detect_wildcard_paths()
    if detected and (not config.get("wildcard_paths") or is_sample_wildcard_config(config.get("wildcard_paths"))):
        config["wildcard_paths"] = detected
    return config


def load_metadata() -> dict[str, Any]:
    ensure_files()
    loaded = load_json(METADATA_PATH, {})
    return loaded if isinstance(loaded, dict) else {}


def save_metadata(metadata: dict[str, Any]) -> None:
    ensure_files()
    temp_path = METADATA_PATH.with_suffix(METADATA_PATH.suffix + ".tmp")
    temp_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(METADATA_PATH)


def resolve_wildcard_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()


def wildcard_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        try:
            root = resolve_wildcard_path(raw_path)
            if not root.exists():
                log(f"wildcard path does not exist: {raw_path} -> {root}")
                continue
            for suffix in ("*.txt", "*.yml", "*.yaml"):
                files.extend(sorted(root.rglob(suffix)))
        except Exception as exc:
            log(f"failed to scan wildcard path {raw_path}: {exc}")
    return files


def best_relative(path: Path, roots: list[str]) -> str:
    for raw_root in roots:
        try:
            return path.relative_to(resolve_wildcard_path(raw_root)).as_posix()
        except Exception:
            continue
    return path.name


def category_from_relative(relative_file: str) -> str:
    path = Path(relative_file)
    stem_path = path.with_suffix("")
    return stem_path.as_posix()


def content_hash(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]


def normalize_text(value: str) -> str:
    value = value.lower().replace("\\", "/")
    value = re.sub(r"\.[a-z0-9]+$", "", value)
    value = re.sub(r"_[0-9a-f]{6,}$", "", value)
    value = re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def safe_filename(value: str, fallback: str = "wildcard") -> str:
    return (normalize_text(value) or fallback)[:120]


def make_item(relative_file: str, line_number: int, prompt: str, source_path: Path, path_hint: str = "") -> dict[str, Any]:
    category = category_from_relative(relative_file)
    raw_path = f"{relative_file}:{line_number}"
    prompt = str(prompt).strip()
    return {
        "id": f"wildcard:{raw_path}",
        "source_type": "wildcard",
        "display_name": prompt,
        "category_path": category,
        "prompt": prompt,
        "source_file": relative_file,
        "line_number": line_number,
        "raw_path": raw_path,
        "content_hash": content_hash(prompt),
        "path_hint": path_hint,
        "absolute_source_file": str(source_path),
    }


def parse_txt_file(path: Path, relative_file: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            text = line.strip()
            if not text or text.startswith("#") or text.startswith("//"):
                continue
            items.append(make_item(relative_file, line_number, text, path))
    except Exception as exc:
        log(f"skipped txt wildcard {path}: {exc}")
    return items


def yaml_leaf_items(node: Any, path_parts: list[str], out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            yaml_leaf_items(value, path_parts + [str(key)], out)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                yaml_leaf_items(item, path_parts, out)
            else:
                text = str(item).strip()
                if text:
                    out.append(("/".join(path_parts), text))
    else:
        text = str(node).strip() if node is not None else ""
        if text:
            out.append(("/".join(path_parts), text))


def parse_yaml_file(path: Path, relative_file: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))
        leaves: list[tuple[str, str]] = []
        yaml_leaf_items(data, [], leaves)
        for index, (path_hint, prompt) in enumerate(leaves, start=1):
            items.append(make_item(relative_file, index, prompt, path, path_hint=path_hint))
    except Exception as exc:
        log(f"skipped yaml wildcard {path}: {exc}")
    return items


def load_wildcard_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_paths = config.get("wildcard_paths", [])
    if not isinstance(raw_paths, list):
        raw_paths = []
    roots = [str(path) for path in raw_paths]
    items: list[dict[str, Any]] = []
    for path in wildcard_files(roots):
        relative_file = best_relative(path, roots)
        suffix = path.suffix.lower()
        if suffix == ".txt":
            items.extend(parse_txt_file(path, relative_file))
        elif suffix in {".yml", ".yaml"}:
            items.extend(parse_yaml_file(path, relative_file))
    return items


def preview_image_index() -> dict[str, str]:
    index: dict[str, str] = {}
    try:
        for path in sorted(PREVIEWS_DIR.rglob("*")):
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            rel = path.relative_to(BASE_DIR).as_posix()
            key = normalize_text(path.stem)
            if key and key not in index:
                index[key] = rel
    except Exception as exc:
        log(f"preview image scan failed: {exc}")
    return index


def load_image_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        for mapping_name in IMAGE_MAPPING_NAMES:
            for path in PREVIEWS_DIR.rglob(mapping_name):
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    log(f"failed to load image mapping {path}: {exc}")
                    continue
                if not isinstance(loaded, dict):
                    continue
                base_dir = path.parent
                base_path = BASE_DIR.resolve()
                for prompt, filename in loaded.items():
                    prompt_key = str(prompt).strip()
                    filename_text = str(filename).strip()
                    if not prompt_key or not filename_text:
                        continue
                    image_path = (base_dir / filename_text).resolve()
                    try:
                        rel_path = image_path.relative_to(base_path)
                    except ValueError:
                        continue
                    if image_path.suffix.lower() not in IMAGE_EXTENSIONS or not image_path.exists():
                        continue
                    mapping[prompt_key] = rel_path.as_posix()
    except Exception as exc:
        log(f"image mapping scan failed: {exc}")
    return mapping


def find_preview_image(item: dict[str, Any], image_index: dict[str, str]) -> str:
    candidates = [
        item.get("raw_path", ""),
        item.get("source_file", ""),
        f"{item.get('source_file', '')}_{item.get('prompt', '')}",
        item.get("prompt", ""),
        item.get("display_name", ""),
    ]
    normalized = [normalize_text(str(candidate)) for candidate in candidates if str(candidate)]
    for candidate in normalized:
        if candidate in image_index:
            return image_index[candidate]
    for key, rel in image_index.items():
        if any(candidate and (candidate in key or key in candidate) for candidate in normalized):
            return rel
    return ""


def merge_metadata(
    item: dict[str, Any],
    metadata: dict[str, Any],
    image_index: dict[str, str],
    image_mapping: dict[str, str],
) -> dict[str, Any]:
    meta = metadata.get(item["id"], {})
    if not isinstance(meta, dict):
        meta = {}
    merged = dict(item)
    merged["display_name_effective"] = meta.get("display_name_override") or item["display_name"]
    merged["prepend_prompt"] = meta.get("prepend_prompt") or ""
    merged["append_prompt"] = meta.get("append_prompt") or ""
    merged["append_negative"] = meta.get("append_negative") or ""
    merged["tags"] = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    merged["memo"] = meta.get("memo") or ""
    merged["image"] = meta.get("image") or image_mapping.get(str(item.get("prompt", "")).strip(), "") or find_preview_image(item, image_index)
    return merged


def compose_prompt(item: dict[str, Any], separator: str) -> str:
    parts = [item.get("prepend_prompt", ""), item.get("prompt", ""), item.get("append_prompt", "")]
    return separator.join([str(part).strip() for part in parts if str(part).strip()])


def search_blob(item: dict[str, Any]) -> str:
    fields = [
        item.get("display_name", ""),
        item.get("display_name_effective", ""),
        item.get("category_path", ""),
        item.get("prompt", ""),
        item.get("prepend_prompt", ""),
        item.get("append_prompt", ""),
        item.get("append_negative", ""),
        " ".join([str(tag) for tag in item.get("tags", [])]),
        item.get("memo", ""),
        item.get("source_file", ""),
        str(item.get("line_number", "")),
    ]
    return " ".join(str(field) for field in fields).lower()


def load_wildcard_prompt_selector_cards() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = load_config()
    metadata = load_metadata()
    image_index = preview_image_index()
    image_mapping = load_image_mapping()
    raw_items = load_wildcard_items(config)
    max_cards = int(config.get("max_cards") or 0)
    if max_cards > 0 and len(raw_items) > max_cards:
        log(f"wildcard items capped: {max_cards}/{len(raw_items)}. Set max_cards to 0 for unlimited.")
        raw_items = raw_items[:max_cards]
    return [merge_metadata(item, metadata, image_index, image_mapping) for item in raw_items], config


def wildcard_prompt_selector_item_map() -> dict[str, dict[str, Any]]:
    items, _ = load_wildcard_prompt_selector_cards()
    return {str(item["id"]): item for item in items}


def metadata_entry_for_save(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    entry = dict(existing) if isinstance(existing, dict) else {}
    for field in ["image", "display_name_override", "prepend_prompt", "append_prompt", "append_negative", "memo"]:
        if field in payload:
            entry[field] = str(payload.get(field) or "")
    if "tags" in payload:
        tags = payload.get("tags")
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.split(",")]
        if isinstance(tags, list):
            entry["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
    return {key: value for key, value in entry.items() if value not in ("", [], None)}


def save_image_data_url(data_url: str, original_name: str, item: dict[str, Any]) -> str:
    match = re.match(r"^data:(?P<mime>image/(?:png|jpeg|jpg|webp));base64,(?P<data>.+)$", data_url or "", re.DOTALL)
    if not match:
        raise ValueError("Unsupported image data")
    mime = match.group("mime").replace("image/jpg", "image/jpeg")
    ext = mimetypes.guess_extension(mime) or Path(original_name or "").suffix.lower()
    if ext == ".jpe":
        ext = ".jpg"
    if ext.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Unsupported image extension")
    raw = base64.b64decode(match.group("data"), validate=True)
    if len(raw) > 40 * 1024 * 1024:
        raise ValueError("Image is too large")
    base_name = safe_filename(str(item.get("raw_path") or item.get("prompt") or item.get("id")))
    target = CUSTOM_PREVIEWS_DIR / f"{base_name}{ext}"
    counter = 2
    while target.exists():
        target = CUSTOM_PREVIEWS_DIR / f"{base_name}_{counter}{ext}"
        counter += 1
    target.write_bytes(raw)
    return target.relative_to(BASE_DIR).as_posix()


class ExtraNetworksPageVisualWildcard(ui_extra_networks.ExtraNetworksPage):
    def __init__(self):
        config = load_config()
        super().__init__(str(config.get("extra_networks_tab_name") or "Wildcard Prompt Selector"))
        self.allow_negative_prompt = False
        self._config = config

    def refresh(self):
        self._config = load_config()

    def create_item(self, item: dict[str, Any], index: int = 0) -> dict[str, Any]:
        separator = str(self._config.get("append_separator", ", "))
        prompt = compose_prompt(item, separator)
        image_rel = str(item.get("image", ""))
        image_path = BASE_DIR / image_rel if image_rel else None
        has_image = bool(image_path and image_path.exists())
        name = str(item.get("display_name_effective") or item.get("display_name") or item.get("id"))
        category = str(item.get("category_path") or "Root")
        source = str(item.get("source_file") or "")
        line_number = str(item.get("line_number") or "")
        filename = str(image_path if has_image else PREVIEWS_DIR / "placeholder.png")
        preview = self.link_preview(str(image_path)) if has_image else None
        description_parts = [str(item.get("prompt") or ""), category, f"{source}: line {line_number}"]
        tags = [f"#{tag}" for tag in item.get("tags", [])]
        if tags:
            description_parts.append(" ".join(tags))

        return {
            "name": name,
            "vw_id": str(item.get("id", "")),
            "vw_category": category,
            "vw_source": source,
            "vw_line": line_number,
            "vw_tags": ",".join(str(tag) for tag in item.get("tags", [])),
            "vw_has_image": "1" if has_image else "0",
            "filename": filename,
            "shorthash": str(item.get("content_hash", ""))[:8],
            "preview": preview,
            "description": "\n".join(part for part in description_parts if part),
            "search_terms": [search_blob(item), category, source, line_number],
            "prompt": quote_js(prompt),
            "local_preview": str(image_path if has_image else PREVIEWS_DIR / f"{safe_filename(name)}.preview.{shared.opts.samples_format}"),
            "sort_keys": {
                "default": index,
                "name": name.lower(),
                "path": str(item.get("raw_path", "")).lower(),
                "date_created": 0,
                "date_modified": 0,
            },
        }

    def create_item_html(self, tabname: str, item: dict, template=None):
        rendered = super().create_item_html(tabname, item, template)
        if not isinstance(rendered, str):
            return rendered
        attrs = (
            f'data-vw-id="{html.escape(item.get("vw_id", ""), quote=True)}" '
            f'data-vw-category="{html.escape(item.get("vw_category", ""), quote=True)}" '
            f'data-vw-source="{html.escape(item.get("vw_source", ""), quote=True)}" '
            f'data-vw-line="{html.escape(item.get("vw_line", ""), quote=True)}" '
            f'data-vw-tags="{html.escape(item.get("vw_tags", ""), quote=True)}" '
            f'data-vw-has-image="{html.escape(item.get("vw_has_image", "0"), quote=True)}"'
        )
        rendered = rendered.replace('<div class="card"', f'<div class="card vw-extra-card" {attrs}', 1)
        buttons = (
            '<button type="button" class="vw-card-tool vw-preview-button" title="Preview">View</button>'
            '<button type="button" class="vw-card-tool vw-edit-button" title="Edit Wildcard Prompt Selector metadata">Edit</button>'
        )
        rendered = rendered.replace('<div class="button-row">', f'<div class="button-row">{buttons}', 1)
        return rendered

    def create_tree_view_html(self, tabname: str) -> str:
        by_source: dict[str, list[dict[str, Any]]] = {}
        for item in self.items.values():
            source = str(item.get("vw_source") or "unknown.txt")
            by_source.setdefault(source, []).append(item)

        def tree_button(label: str, data_path: str, subclass: str, is_dir: bool = False) -> str:
            return self.btn_tree_tpl.format(
                **{
                    "search_terms": [data_path, label],
                    "subclass": subclass,
                    "tabname": tabname,
                    "extra_networks_tabname": self.extra_networks_tabname,
                    "onclick_extra": "",
                    "data_path": data_path,
                    "data_hash": "",
                    "action_list_item_action_leading": "<i class='tree-list-item-action-chevron'></i>",
                    "action_list_item_visual_leading": "",
                    "action_list_item_label": label,
                    "action_list_item_visual_trailing": "",
                    "action_list_item_action_trailing": "",
                }
            )

        folders: dict[str, set[str]] = {}
        root_files: set[str] = set()
        for source in by_source:
            source_path = Path(source)
            folder = source_path.parent.as_posix()
            filename = source_path.name
            if folder in ("", "."):
                root_files.add(source)
            else:
                folders.setdefault(folder, set()).add(source)

        html_parts: list[str] = []
        for folder, files in sorted(folders.items(), key=lambda pair: shared.natural_sort_key(pair[0])):
            children = []
            for source in sorted(files, key=shared.natural_sort_key):
                filename = Path(source).name
                children.append(
                    "<li class='tree-list-item tree-list-item--subitem' data-tree-entry-type='file'>"
                    f"{tree_button(filename, source, 'tree-list-content-file vw-source-file')}"
                    "</li>"
                )
            parent = tree_button(folder, folder + "/", "tree-list-content-dir vw-source-folder", is_dir=True)
            html_parts.append(
                "<li class='tree-list-item tree-list-item--has-subitem' data-tree-entry-type='dir'>"
                f"{parent}<ul class='tree-list tree-list--subgroup' hidden>{''.join(children)}</ul>"
                "</li>"
            )

        for source in sorted(root_files, key=shared.natural_sort_key):
            html_parts.append(
                "<li class='tree-list-item' data-tree-entry-type='file'>"
                f"{tree_button(source, source, 'tree-list-content-file vw-source-file')}"
                "</li>"
            )
        return f"<ul class='tree-list tree-list--tree vw-source-tree'>{''.join(html_parts)}</ul>"

    def list_items(self):
        try:
            self._config = load_config()
            items, _ = load_wildcard_prompt_selector_cards()
            for index, item in enumerate(items):
                yield self.create_item(item, index)
        except Exception as exc:
            log(f"Extra Networks list_items failed: {exc}")

    def allowed_directories_for_previews(self):
        return [str(PREVIEWS_DIR)]


def on_before_ui():
    try:
        config = load_config()
        if not config.get("enable_extra_networks_integration", True):
            return
        tab_name = str(config.get("extra_networks_tab_name") or "Wildcard Prompt Selector").lower()
        if not any(getattr(page, "name", "") == tab_name for page in ui_extra_networks.extra_pages):
            ui_extra_networks.register_page(ExtraNetworksPageVisualWildcard())
            log("registered Wildcard Prompt Selector Extra Networks page")
    except Exception as exc:
        log(f"failed to register Extra Networks page: {exc}")


script_callbacks.on_before_ui(on_before_ui)


def api_get_item(request: Request):
    try:
        item_id = request.query_params.get("id", "")
        item = wildcard_prompt_selector_item_map().get(item_id)
        if not item:
            return JSONResponse({"error": "Item not found"}, status_code=404)
        return JSONResponse({"item": item})
    except Exception as exc:
        log(f"api_get_item failed: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_save_item(request: Request):
    try:
        payload = await request.json()
        item_id = str(payload.get("id") or "")
        item = wildcard_prompt_selector_item_map().get(item_id)
        if not item:
            return JSONResponse({"error": "Item not found"}, status_code=404)
        metadata = load_metadata()
        existing = metadata.get(item_id, {})
        entry = metadata_entry_for_save(payload, existing)
        data_url = str(payload.get("image_data_url") or "")
        if data_url:
            entry["image"] = save_image_data_url(data_url, str(payload.get("image_name") or ""), item)
        if payload.get("clear_image"):
            entry["image"] = ""
        if entry:
            metadata[item_id] = entry
        elif item_id in metadata:
            del metadata[item_id]
        save_metadata(metadata)
        return JSONResponse({"ok": True, "metadata": metadata.get(item_id, {})})
    except Exception as exc:
        log(f"api_save_item failed: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


def on_app_started(_demo, app):
    try:
        app.add_api_route("/wildcard-prompt-selector/item", api_get_item, methods=["GET"])
        app.add_api_route("/wildcard-prompt-selector/save", api_save_item, methods=["POST"])
        log("registered Wildcard Prompt Selector API routes")
    except Exception as exc:
        log(f"failed to register API routes: {exc}")


script_callbacks.on_app_started(on_app_started)


class Script(scripts.Script):
    def title(self):
        return "wildcard_prompt_selector"

    def show(self, is_img2img):
        return False

