# Wildcard Prompt Selector

Wildcard Prompt Selector is a Stable Diffusion WebUI Forge/ReForge/AUTOMATIC1111 extension that shows wildcard candidate lines as searchable Extra Networks cards. Large wildcard folders are loaded on demand from the left folder tree.

It reads wildcard files in read-only mode. Source wildcard files are not edited.

## Quick Start

### Install From URL

In WebUI / reForge, open **Extensions > Install from URL** and use:

```text
URL for extension's git repository:
https://github.com/dr1610/wildcard-prompt-selector

Specific branch name:
main

Local directory name:
wildcard_prompt_selector
```

Then click **Install**, restart WebUI, and hard-refresh the browser with `Ctrl + F5`.

If URL installation fails, the repository itself may still be fine. Common causes are that WebUI cannot find the `git` command, a folder with the same name already exists, or the local directory name was auto-detected incorrectly.

### Install From ZIP

If Git installation does not work:

1. Open this repository on GitHub.
2. Click **Code > Download ZIP**.
3. Extract the ZIP.
4. Rename the extracted folder to:

```text
wildcard_prompt_selector
```

5. Copy it into your WebUI `extensions` directory:

```text
stable-diffusion-webui/extensions/wildcard_prompt_selector
```

6. Restart WebUI.
7. Open the Extra Networks area and select the `Wildcard Prompt Selector` tab.

The package includes `sample_wildcards`, so the tab can open even when Dynamic Prompts is not installed yet.

## First-Run Detection

On startup, the extension tries to use a real wildcard folder when it is found next to this extension:

```text
extensions/sd-dynamic-prompts/wildcards
extensions/stable-diffusion-webui-wildcards/wildcards
extensions/wildcards
```

If one of those folders exists and `config.json` still points only to `sample_wildcards`, Wildcard Prompt Selector automatically uses the detected folder. If nothing is found, it falls back to the bundled samples.

To force a custom folder, edit `config.json`:

```json
{
  "wildcard_paths": [
    "../sd-dynamic-prompts/wildcards"
  ]
}
```

Relative paths are resolved from the Wildcard Prompt Selector extension folder.

## Behavior

- Click a card to insert the wildcard candidate text directly into the prompt.
- The extension inserts candidate text, not `__wildcard__` syntax.
- `.txt`, `.yml`, and `.yaml` wildcard files are supported.
- Large wildcard libraries are loaded on demand from the left tree; `max_cards` defaults to `0`.
- Optional preview images can be placed under `previews/`.

## Files Written Locally

The extension writes only inside its own folder:

- `config.json`
- `wildcard_prompt_selector_metadata.json`
- `previews/`

It does not modify Dynamic Prompts wildcard files or other extensions.

## Troubleshooting

If the tab still shows only samples after installing Dynamic Prompts, check `config.json`. If it contains a custom path, that custom setting is respected. Set it to your wildcard folder or delete `config.json` and restart WebUI to regenerate it.

After updating the extension JavaScript, restart WebUI and hard-refresh the browser with `Ctrl + F5`.

## License

MIT License. See `LICENSE` for details.

