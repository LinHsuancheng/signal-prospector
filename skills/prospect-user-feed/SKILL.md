---
name: prospect-user-feed
description: Use when collecting and scoring a specific user's answers or posts from a supported social platform with Signal Prospector.
---

# Prospect a User Feed

Turn a platform plus user identity into a verified Prospector run. The output is a set of high-value answers in a user-approved Inbox.

## Inputs

Require:

- platform, for example `zhihu`;
- user URL or stable handle;
- maximum number of new answers to process, or an explicit choice to process all discovered answers;
- Inbox path. If it is missing or ambiguous, ask before doing any scoring or writes.

Treat a user profile URL as an identity hint, not automatically as the crawl URL. Resolve the platform's answer-only or post-only feed first.

## Workflow

1. Read the project's README, `config.toml`, scoring prompt, and Prospector entry point. Preserve the existing database, prompt, model, threshold, and Chrome profile unless the user explicitly changes them.
2. Resolve a platform-specific feed:
   - Zhihu: use `https://www.zhihu.com/people/<id>/answers` for answers.
   - Do not use `https://www.zhihu.com/people/<id>` as an answer source. It is a dynamic feed and can include answers merely liked by the user.
   - Match answer URLs with `^https://www\\.zhihu\\.com/question/[0-9]+/answer/[0-9]+`.
   - Omit `group_pattern` for a user's answer feed unless the user explicitly wants at most one answer per question.
3. Check that the existing Chrome/CDP session is reachable and logged in. Prefer the configured CDP endpoint; do not silently create a fresh profile that would lose the user's identity.
4. Run a discovery-only pass. It may navigate the browser and extract candidate text, but it must not call the scoring API, mark URLs processed, modify SQLite, or write the Inbox.
5. Verify provenance before scoring:
   - the page is the intended user's answer/post feed;
   - candidate URLs have the expected platform shape;
   - visible author markers, when available, match the requested user;
   - profile activity, liked content, recommendations, and other authors are excluded.
   If provenance cannot be established, stop and report the ambiguity.
6. Present a preflight summary and wait for explicit confirmation. Include:
   - platform and user;
   - source URL;
   - discovered candidate count;
   - requested processing count and the actual count available;
   - resolved absolute Inbox path;
   - model, score threshold, and whether existing processed URLs will be skipped.
7. After confirmation, run Prospector with the resolved source and `--number` when a limit was given. Prefer a temporary run config with absolute paths over editing the checked-in `config.toml`; if the project already has an explicit source configuration, reuse it.
8. Report processed, scored, saved, and failed counts, plus the Inbox path. Do not run `organize` automatically; human review belongs after the Inbox is populated.

## Safety and correctness

- Never score or write before the preflight confirmation.
- Never invent an Inbox location. A default is allowed only when the user has explicitly established it in project configuration and the preflight shows the resolved path.
- Keep URL deduplication and the existing SQLite state enabled.
- If the platform is unsupported, inspect the page structure and state what adapter is missing; do not guess selectors and run production scoring.
- A discovery count is not a promise that every candidate will survive extraction or scoring. Report the final counts separately.

## Minimal Zhihu page shape

```toml
[[pages]]
name = "zhihu-user-answers"
url = "https://www.zhihu.com/people/<id>/answers"
link_pattern = "^https://www\\.zhihu\\.com/question/[0-9]+/answer/[0-9]+"
scrolls = 3
rounds = 1
scroll_delta = 1400
scroll_wait_seconds = 5
content_stop_markers = ["更多回答"]
```

The page name is only a run label; the user identity must still be checked from the page and candidate metadata.
