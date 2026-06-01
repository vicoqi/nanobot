Update `{{ plan_path }}` based on the analysis below.

## Allowed file path (relative to workspace root)
- `{{ plan_path }}`

Do NOT edit any other file.

## Editing rules
- Edit directly — the current plan contents are provided below, no read_file needed
- Keep `# Fixed Contract` intact
- Edit only frontmatter and the Dream-managed sections beneath it
- Prefer one batched `edit_file` call; use `write_file` only if the plan is truly missing
- Use exact text as old_text, include surrounding blank lines for unique match
- Surgical edits only — never rewrite the entire file unless it is missing
- If nothing should change, stop without calling tools

## Plan rules
- Maintain durable proactive-delivery strategy, not today's final user-facing message
- The plan may describe an informative update, a contextual check-in, or a grounded offer of help
- Prefer strong signals from the conversation history, but low-confidence candidates are acceptable
- Keep the first candidate backup concrete enough that the executor could use it when `Active Delivery` is empty
- Use `status: inactive` only when the evidence says proactive delivery should pause, stop, or remain disabled
- When evidence is partial, prefer a cautious candidate backup over leaving the plan empty
- Preserve stable structure and concise bullets
