
---

## 2）`AGENTS.md`

```md
# AGENTS.md

## Project
zenn-bot / dual-platform auto publishing system

## Goal
Maintain the existing Windows local publishing workflow for:

- Zenn
- Hatenablog

Do not redesign working flows unless explicitly requested.

## Current architecture
- Feishu Base is the single topic pool.
- Zenn flow:
  - read Feishu record
  - generate Japanese article
  - write local markdown
  - git commit / push
  - GitHub deploy to Zenn
  - write back status to Feishu
- Hatenablog flow:
  - read Feishu record
  - generate Japanese article
  - publish via AtomPub API
  - write back status to Feishu

## Important paths
- Project dir: `E:\yanque\海外投放\zenn-bot`
- Zenn repo dir: `E:\yanque\海外投放\zen\takkenai-zenn`

## Important files
- `main.py`
- `feishu_client.py`
- `generator.py`
- `image_manager.py`
- `link_inserter.py`
- `retry_manager.py`
- `publish_gate.py`
- `git_publisher.py`
- `zenn_writer.py`
- `hatena_writer.py`
- `hatena_client.py`
- `hatena_publisher.py`
- `bot_notifier.py`
- `run_publish.bat`

## Working rules
1. Prefer minimal-risk changes.
2. Do not rewrite the whole project unless the user explicitly asks.
3. Prefer full-file replacement for Python file edits.
4. Do not ask the user to manually patch many scattered lines.
5. Preserve current Feishu field mapping unless explicitly asked to change it.
6. Never expose secrets from `.env`.
7. Keep explanations simple and operation-oriented.

## Publishing rules
### Zenn
- Supported statuses:
  - `ready`
  - `queued`
  - `waiting`
  - `published`
  - `failed`
- Respect publish gate logic.
- Do not bypass queued / waiting logic.
- Do not remove local quota protection.

### Hatenablog
- Publish via AtomPub API.
- Preserve current blog_id / endpoint logic unless necessary.
- Do not redesign the publish flow if it already works.

## Article generation rules
- Output must be full Japanese Markdown article.
- Do not force JSON output.
- Keep quality gate enabled.
- Avoid outline-like output, placeholders, or template text.
- Kimi / Moonshot compatibility matters.

## Link insertion rules
- Prefer keywords-based homepage linking.
- Homepage URL:
  - `https://www.takkenai.jp/`
- Brand mention is optional.
- If brand is mentioned, it should be natural.
- Avoid overly dense links.

## Retry rules
- Quality failure should not instantly become permanent failure.
- Retry after 1 hour.
- Maximum 3 quality retries.
- If still failing after max retries, mark as `failed`.

## Known risk areas
- `run_publish.bat`
- `.publish.lock`
- old Python process residue
- Windows Task Scheduler
- duplicate publish protection
- Hatena long-form generation stability

## Output style
When the user asks for code changes:
- First explain the change goal briefly.
- Then provide complete replacement code.
- Avoid partial diff unless the user explicitly asks for diff.
- Keep code compatible with existing files and env names.

## What not to do
- Do not invent missing business logic.
- Do not silently change Feishu field names.
- Do not hardcode secrets.
- Do not remove working status transitions.
- Do not propose large refactors by default.