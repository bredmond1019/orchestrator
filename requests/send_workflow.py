"""Send a workflow event to the orchestration API.

Interactive helper for triggering the five production workflows from the CLI.
Reads ORCHESTRATION_API_KEY from app/.env automatically.

Usage examples:
    # Content pipeline — digest a YouTube video
    python requests/send_workflow.py content --url "https://www.youtube.com/watch?v=..."

    # Content pipeline — digest + blog post
    python requests/send_workflow.py content --url "https://example.com/article" --blog

    # Research agent
    python requests/send_workflow.py research --company "Notion"

    # Proposal generator (Portuguese output)
    python requests/send_workflow.py proposal \
        --company "Acme Clinic" \
        --industry "Healthcare" \
        --description "25-person private clinic in São Paulo" \
        --language PT

    # Document ingest (text)
    python requests/send_workflow.py ingest \
        --title "My Doc" \
        --text "The full document text goes here..."

    # Document Q&A
    python requests/send_workflow.py qa \
        --doc-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
        --question "What is this about?" \
        --session-id "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

    # Q&A against brain corpus
    python requests/send_workflow.py qa \
        --doc-id "00000000-0000-0000-0000-000000000000" \
        --question "What is my current rate strategy?" \
        --corpus brain
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_ENV = _REPO_ROOT / "app" / ".env"
BASE_URL = "http://localhost:8080/events/"


def _load_api_key() -> str | None:
    key = os.environ.get("ORCHESTRATION_API_KEY")
    if key:
        return key
    if _APP_ENV.exists():
        for line in _APP_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ORCHESTRATION_API_KEY="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return None


def _post(workflow_type: str, data: dict) -> None:
    payload = {"workflow_type": workflow_type, "data": data}
    api_key = _load_api_key()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    print(f"→ POST {BASE_URL}")
    print(f"  workflow_type : {workflow_type}")
    print(f"  data          : {json.dumps(data, indent=2)}")
    print()

    response = requests.post(BASE_URL, json=payload, headers=headers)
    print(f"Status   : {response.status_code}")
    try:
        print(f"Response : {json.dumps(response.json(), indent=2)}")
    except Exception:
        print(f"Response : {response.text}")

    if response.status_code == 401:
        print("\nHint: set ORCHESTRATION_API_KEY in app/.env")
    elif response.status_code == 422:
        print("\nValidation error — check your payload fields.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a workflow event to the orchestration API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="workflow", required=True)

    # content
    p = sub.add_parser("content", help="CONTENT_PIPELINE — ingest a URL")
    p.add_argument("--url", required=True, help="YouTube or article URL")
    p.add_argument("--blog", action="store_true", default=False, help="Generate blog post")

    # research
    p = sub.add_parser("research", help="RESEARCH_AGENT — research a company")
    p.add_argument("--company", required=True, help="Company name to research")

    # proposal
    p = sub.add_parser("proposal", help="PROPOSAL_GENERATOR — generate a proposal")
    p.add_argument("--company", required=True)
    p.add_argument("--industry", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--language", default="PT", choices=["PT", "EN"])
    p.add_argument("--notes", default=None, help="Optional diagnostic intake notes")

    # ingest
    p = sub.add_parser("ingest", help="DOCUMENT_INGEST — ingest a document")
    p.add_argument("--title", required=True, help="Document title")
    p.add_argument("--text", default=None, help="Document text (use --text or --file)")
    p.add_argument("--file", default=None, help="Path to a .txt file to ingest")
    p.add_argument("--chunk-size", type=int, default=500)
    p.add_argument("--overlap", type=int, default=50)

    # qa
    p = sub.add_parser("qa", help="DOCUMENT_QA — ask a question")
    p.add_argument("--doc-id", required=True, help="UUID of the ingested document")
    p.add_argument("--question", required=True)
    p.add_argument("--session-id", default=None, help="Session UUID (for memory continuity)")
    p.add_argument("--corpus", default="content", choices=["content", "brain"])

    args = parser.parse_args()

    if args.workflow == "content":
        _post("CONTENT_PIPELINE", {"url": args.url, "make_blog": args.blog})

    elif args.workflow == "research":
        _post("RESEARCH_AGENT", {"company_name": args.company})

    elif args.workflow == "proposal":
        data: dict = {
            "company_name": args.company,
            "industry": args.industry,
            "description": args.description,
            "language": args.language,
        }
        if args.notes:
            data["intake_notes"] = args.notes
        _post("PROPOSAL_GENERATOR", data)

    elif args.workflow == "ingest":
        if args.text:
            content = args.text
        elif args.file:
            content = Path(args.file).read_text(encoding="utf-8")
        else:
            print("Error: provide --text or --file", file=sys.stderr)
            sys.exit(1)
        _post("DOCUMENT_INGEST", {
            "title": args.title,
            "content": content,
            "chunk_size": args.chunk_size,
            "overlap": args.overlap,
        })

    elif args.workflow == "qa":
        data = {
            "doc_id": args.doc_id,
            "question": args.question,
            "corpus": args.corpus,
        }
        if args.session_id:
            data["session_id"] = args.session_id
        _post("DOCUMENT_QA", data)


if __name__ == "__main__":
    main()
