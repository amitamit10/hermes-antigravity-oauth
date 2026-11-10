# hermes-antigravity-oauth

[![npm](https://img.shields.io/npm/v/hermes-antigravity-oauth?logo=npm)](https://www.npmjs.com/package/hermes-antigravity-oauth)
[![release](https://github.com/amitamit10/hermes-antigravity-oauth/actions/workflows/release.yml/badge.svg)](https://github.com/amitamit10/hermes-antigravity-oauth/actions/workflows/release.yml)
[![license](https://img.shields.io/github/license/amitamit10/hermes-antigravity-oauth)](LICENSE)

Run [Hermes Agent](https://hermes-agent.nousresearch.com) on your Google Antigravity plan (Gemini 3.x, Claude 4.6, GPT-OSS) with a single sign-in.

```bash
hermes plugins install https://github.com/amitamit10/hermes-antigravity-oauth --enable
hermes auth add antigravity-oauth
hermes --provider antigravity-oauth -m gemini-3.8-flash-low
```

## Key Features

- **Official Google Antigravity CLI Integration**: Every request runs via the official `agy` CLI binary using your authorized Google account. The plugin never touches, copies, or uploads your OAuth token.
- **Thinking Mode & Reasoning Separation**: Transparently parses model reasoning blocks (`<thought>...</thought>`, `<thinking>...</thinking>`) and structured thinking events into Hermes native `delta.reasoning_content` channel. Model reasoning stays in Hermes collapsible thinking UI and never leaks into user text or corrupts tool arguments.
- **Multimodal Documents & Files**: First-class support for attached documents, files, images, and attachments (`type: "document"`, `type: "file"`, `type: "attachment"`, `file_path`, `file_url`). Files are cached safely and referenced as native `@path` markers in the models isolated workspace.
- **Native Tool Bridging & Sandboxing**: Antigravity internal tools are safely intercepted and re-issued as native Hermes tools running under your configured sandbox and approval settings:
  - `run_command` → `terminal`
  - `view_file` → `read_file`
  - `edit_file` → `patch`
  - `grep_search` / `find_by_name` → `search_files`
  - `write_to_file` → `write_file`
  - `search_web` → `web_search`
  - `read_url_content` → `web_extract`
  - Any unmapped native tool is neutralized before host execution.
- **SOUL & Persona Delivery**: Writes Hermes system prompt and persona (`$HERMES_HOME/SOUL.md`) into the per-session private workspace as `GEMINI.md`, which `agy` loads as first-class instructions.
- **Quota & Usage Telemetry**: `/usage` and `hermes usage` query `agy` quota API directly with cross-platform Python 3.10–3.14 support for ISO 8601 reset timestamps (`Z` suffix and sub-microsecond precision).
- **Headless / Remote Login Helper**: Includes `scripts/remote-login.py` for headless VPS and SSH servers where interactive browser access is unavailable.

## How It Works

- **Calls belong to agy**: Requests are dispatched to `agy` subprocesses in an isolated temp HOME.
- **Keyring & Token Isolation**: The plugin symlinks the credential file (`antigravity-oauth-token`) or macOS keychain into the temp HOME and probes credential presence via OS keyring tools (`secret-tool`, `security`, `cmdkey`) without reading secrets. The workspace is cleaned up automatically on session exit.
- **Process Supervision**: Cleanly unblocks streaming reader threads, enforces host timeout budgets, and prevents orphaned child processes.

## Install

Requirements: Hermes Agent (`>=0.21.0`), plus the Antigravity CLI (`agy`) from <https://antigravity.google/cli>.

| Route | Command |
|---|---|
| Hermes CLI (recommended) | `hermes plugins install https://github.com/amitamit10/hermes-antigravity-oauth --enable` then `hermes auth add antigravity-oauth` |
| npx installer | `npx hermes-antigravity-oauth` (add `--yes` to install agy if missing) |

## Auth Commands

| Command | Effect |
|---|---|
| `hermes auth add antigravity-oauth` | Runs agy Google sign-in flow and verifies live |
| `hermes auth status antigravity-oauth` | Live check through `agy models` |
| `hermes auth logout antigravity-oauth` | Guides logout through `agy /logout` |

Aliases: `google-antigravity`, `agy-oauth`.

### Headless / Remote Login

When running Hermes on a remote server or VPS over SSH:

```bash
git clone https://github.com/amitamit10/hermes-antigravity-oauth
python3 hermes-antigravity-oauth/scripts/remote-login.py --code-file /tmp/agy-code.txt &
# Open the printed LOGIN_URL in your browser, authorize, then:
printf "%s" "<authorization_code>" > /tmp/agy-code.txt
wait
```

The script manages the PTY interaction, feeds the code the moment it is written, and confirms session status with `agy models`.

## Configuration

| Environment Variable | Default | Purpose |
|---|---|---|
| `ANTIGRAVITY_COMMAND` | `agy` | Custom path to the `agy` binary |
| `ANTIGRAVITY_WORKSPACE_RULES` | `1` | `1` writes `GEMINI.md` in workspace; `0` puts SOUL inline in the prompt |

Gemini models support effort suffixes (e.g. `-low`, `-medium`, `-high`). Claude and GPT-OSS models automatically omit unsupported effort flags.

## Testing & Validation

```bash
# Run full unit test suite
PYTHONPATH=<hermes-agent-src>:. python3 -m unittest discover -s tests -p "test_*.py"

# Validate plugin manifest and compatibility
hermes plugins validate . --json
```

## Credits

- Original streaming client, process isolation, and keyring probes: [soyelmismo/hermes-antigravity-subscription](https://github.com/soyelmismo/hermes-antigravity-subscription) (MIT).
- Initial package structure and npx installer: [neerazz/hermes-antigravity-oauth](https://github.com/neerazz/hermes-antigravity-oauth) (MIT).
- Maintained and extended by [amitamit10](https://github.com/amitamit10): thinking mode separation, multimodal document attachments, patch tool mapping, robust quota parsing, and headless login.

MIT © 2026
