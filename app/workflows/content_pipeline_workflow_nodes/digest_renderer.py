"""Static-HTML digest renderer for the content_pipeline workflow.

Deliberately dumb: pure functions that write one static HTML page per ingested
item plus a per-category index page. No JavaScript, no search box, no tagging
(D22 — MVP is ingestion + store + dumb display only). The output directory is
supplied by the caller (config/env), never hardcoded to a deployment path
(CLAUDE.md rule 7).
"""

from pathlib import Path


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
    """Render a list of strings as an HTML ``<ul>`` (or a dash when empty)."""
    if not items:
        return "<p>-</p>"
    rows = "".join(f"<li>{_esc(item)}</li>" for item in items)
    return f"<ul>{rows}</ul>"


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
<title>{title}</title>
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
    links = "".join(
        f'<li><a href="{_esc(path.name)}">{_esc(path.stem)}</a></li>' for path in pages
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(category)} digest</title>
</head>
<body>
<h1>{_esc(category)}</h1>
<ul>{links}</ul>
</body>
</html>
"""
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return index_path
