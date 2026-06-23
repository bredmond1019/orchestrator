"""Static-HTML digest renderer for the content_pipeline workflow.

Deliberately dumb: pure functions that write one static HTML page per ingested
item plus a per-category index page. No JavaScript, no search box, no tagging
(D22 — MVP is ingestion + store + dumb display only). The output directory is
supplied by the caller (config/env), never hardcoded to a deployment path
(CLAUDE.md rule 7).
"""

from pathlib import Path

# Shared, dependency-free stylesheet inlined into every generated page. Its job
# is readability: cap the content column so prose does not run edge-to-edge on
# wide screens, and set comfortable line-height/spacing. Every page flows
# through this one renderer, so styling here fixes the format for all output.
_STYLE = """\
<style>
:root { color-scheme: light dark; }
body {
  max-width: 70ch;
  margin: 2rem auto;
  padding: 0 1.25rem;
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: #1a1a1a;
  background: #fafafa;
}
h1 { line-height: 1.25; font-size: 1.7rem; }
h2 { margin-top: 2rem; font-size: 1.25rem; border-bottom: 1px solid #ddd; padding-bottom: 0.25rem; }
li { margin-bottom: 0.5rem; }
a { color: #0b5fff; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #1a1a1a; }
  h2 { border-color: #444; }
  a { color: #6ea8ff; }
}
</style>"""


def _esc(text: str) -> str:
    """Minimal HTML escape for interpolated values."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_list(items: list[str]) -> str:
    """Render a list of strings as an HTML ``<ul>`` (or a dash when empty).

    Each ``<li>`` is emitted on its own line so the generated source stays
    readable in an editor instead of collapsing into one giant horizontal line.
    """
    if not items:
        return "<p>-</p>"
    rows = "\n".join(f"  <li>{_esc(item)}</li>" for item in items)
    return f"<ul>\n{rows}\n</ul>"


def render_artifact_page(artifact: dict, output_dir: Path, category: str) -> Path:
    """Write a single static HTML page for one artifact and return its path.

    The page shows the title, TL;DR, read-time estimate, the structured concept
    lists, and the source URL as a link. The file is named after the artifact's
    id inside the category folder.
    """
    page_dir = output_dir / category
    page_dir.mkdir(parents=True, exist_ok=True)
    page_path = page_dir / f"{artifact['artifact_id']}.html"

    title = _esc(artifact.get("title", "Untitled"))
    source_url = _esc(artifact.get("source_url", ""))
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{_STYLE}
</head>
<body>
<article>
<h1>{title}</h1>
<p><strong>TL;DR:</strong> {_esc(artifact.get("tl_dr", ""))}</p>
<p><strong>Read time:</strong> {_esc(artifact.get("read_time_estimate", ""))}</p>
<p><strong>Category:</strong> {_esc(category)}</p>
<p><strong>Source:</strong> <a href="{source_url}">{source_url}</a></p>
<h2>Core concepts</h2>
{_render_list(artifact.get("core_concepts", []))}
<h2>Key insights</h2>
{_render_list(artifact.get("key_insights", []))}
<h2>Questions raised</h2>
{_render_list(artifact.get("questions_raised", []))}
<h2>Connections to my work</h2>
{_render_list(artifact.get("connections_to_my_work", []))}
<h2>Further exploration</h2>
{_render_list(artifact.get("further_exploration", []))}
</article>
</body>
</html>
"""
    with open(page_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return page_path


def regenerate_category_index(output_dir: Path, category: str) -> Path:
    """Rewrite the index page listing every artifact page in a category.

    Globs the category folder for ``*.html`` (excluding ``index.html``), sorts
    them, and writes an ``index.html`` linking each page by filename stem.
    """
    page_dir = output_dir / category
    page_dir.mkdir(parents=True, exist_ok=True)
    index_path = page_dir / "index.html"

    pages = sorted(
        path for path in page_dir.glob("*.html") if path.name != "index.html"
    )
    links = "\n".join(
        f'  <li><a href="{_esc(path.name)}">{_esc(path.stem)}</a></li>'
        for path in pages
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(category)} digest</title>
{_STYLE}
</head>
<body>
<h1>{_esc(category)}</h1>
<ul>
{links}
</ul>
</body>
</html>
"""
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return index_path
