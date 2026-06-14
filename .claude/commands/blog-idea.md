# Blog Idea — Capture a blog or LinkedIn post idea into planning/blog/BLOG_IDEAS.md.

## Variables

$ARGUMENTS — description of the blog post idea (title hint, angle, or free-form notes).

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the idea.
2. Read `planning/blog/BLOG_IDEAS.md` to understand the current structure and existing entries.
3. Based on `$ARGUMENTS`, determine:
   - A short, punchy working title
   - A one-line hook (the angle or "why this is worth reading")
   - Output target: `[LI]` for LinkedIn-length, `[Blog]` for long-form, or `[Both]`
   - Whether this belongs in **Queued** (ready to write soon) or **Suggested** (needs more project experience first) — default to Queued unless the description implies it requires future work
4. Append the new entry to the `## Queued` or `## Suggested` section of `planning/blog/BLOG_IDEAS.md` using this format:

```
**<Working Title>** `[LI|Blog|Both]`
<One-line hook. Specific angle, audience pain point, or concrete example that makes this worth reading.>
```

5. If the user's description mentions a connection to a specific project, file, or decision, include a brief `Reference:` or `*(Revisit when: ...)*` note on a third line.
6. Report back the title and section it was added to.

7. **Sync the company brain.** Append the same entry to `../docs/content/ideas.md`
   in the company brain:
   - Use the same working title, hook, and output target `[LI|Blog|Both]`.
   - Place it in the **Ideas Backlog — Not Yet Scoped** section (or **Confirmed** /
     **Committed** if the idea is already ready or tied to a named spec).
   - Surgical append only — do not touch other sections.

## Notes

- Step 7 mirrors the idea to the top-level company brain so ideas surfaced in any sub-project
  session are automatically visible at the brain level.
- Never edit existing entries unless the user explicitly asks — only append.
