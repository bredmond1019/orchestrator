---
type: Reference
title: PromptManager — How It Works
description: How PromptManager works — loading .j2 system prompts from app/prompts/.
doc_id: prompt-manager
layer: [engine]
project: python-orchestration
status: active
keywords: [PromptManager, Jinja2, system prompt, j2 templates, prompt_loader]
related: [app-architecture-overview, D34-jinja2-prompts]
---

# PromptManager — How It Works

`app/services/prompt_loader.py`

---

## The big picture

`PromptManager` is how prompts stay out of Python code. Instead of hardcoding a system prompt string inside a node, you write it as a `.j2` file in `app/prompts/`, and `PromptManager` loads and renders it with Jinja2 at runtime.

This matters because:
- Prompts can be edited and hot-reloaded without restarting the server.
- Variables (company name, persona, topic) are injected at render time, not embedded as formatted strings.
- Every `.j2` file carries YAML frontmatter metadata (description, author) that documents the prompt alongside the prompt itself.

The standing rule in CLAUDE.md: **never hardcode a system prompt in Python**. All prompts are `.j2` files loaded via `PromptManager`.

---

## Step 1 — The `.j2` file format

A prompt template looks like this:

```jinja
{# app/prompts/ticket_analysis.j2 #}
---
description: A template for analyzing incoming {{ pipeline | default('customer support') }} tickets
author: TechGear AI Team
---

You're an AI assistant named {{ name | default('Emma') }}, working for {{ company | default('TechGear') }}.
Your goal is to analyze incoming {{ pipeline | default('support') }} tickets and classify their intent.

# CONTEXT
You will be provided with the following information from a {{ pipeline | default('support') }} ticket:
- Sender: The name or identifier of the person who sent the ticket
- Subject: The subject line of the ticket
- Body: The main content of the ticket

# TASK
Your task is to analyze the ticket and determine its primary intent...
```

Two parts separated by `---`:

1. **YAML frontmatter** (between the `---` markers) — metadata about the template. Read by the `python-frontmatter` library.

**Important:** Jinja2 syntax inside the YAML frontmatter block is never rendered. python-frontmatter parses the frontmatter as raw YAML — the string `{{ pipeline | default('customer support') }}` would be stored literally in `post.metadata['description']`. Only `post.content` (the template body after the second `---`) is passed to `env.from_string()` and rendered.

2. **Jinja2 template body** (everything after the second `---`) — the actual prompt text with `{{ variable }}` placeholders.

The `| default('value')` filter means: use this default if the variable wasn't passed in. This makes templates resilient to partial rendering.

---

## Step 2 — The Jinja2 environment singleton

```python
class PromptManager:
    _env = None  # class-level cache

    @classmethod
    def _get_env(cls, templates_dir="prompts") -> Environment:
        templates_dir = Path(__file__).parent.parent / templates_dir
        if cls._env is None:
            cls._env = Environment(
                loader=FileSystemLoader(templates_dir),
                undefined=StrictUndefined,
            )
        return cls._env
```

`_env` is a class-level variable — shared across all instances and calls. The first time `_get_env()` is called, it creates the `Environment` and caches it. Every subsequent call returns the same one. This is a singleton pattern to avoid re-creating the Jinja2 environment on every prompt render.

Key configuration choices:
- **`FileSystemLoader(templates_dir)`** — loads templates from `app/prompts/` on disk. Hot-reload is not provided by FileSystemLoader. The actual mechanism is the explicit open() call and env.from_string(post.content) pattern in get_prompt(). from_string() compiles the template string from scratch each call, bypassing Jinja2's compiled-template cache entirely. FileSystemLoader is used here only as a path resolver (get_source() returns the file path, which is then passed to open()). If env.get_template() were used instead, Jinja2 would cache the compiled template and changes would not be picked up without restart.
- **`StrictUndefined`** — if you call `get_prompt("template", name="Emma")` but the template uses `{{ company }}` and you didn't pass `company=`, Jinja2 raises an error immediately instead of silently rendering `{{ company }}` as an empty string. This catches template/call-site mismatches early.

The templates directory is computed relative to the `prompt_loader.py` file:
```python
Path(__file__).parent.parent / templates_dir
# → app/services/../prompts/ → app/prompts/
```

---

## Step 3 — `get_prompt()`: load, strip frontmatter, render

```python
@staticmethod
def get_prompt(template: str, **kwargs) -> str:
    env = PromptManager._get_env()
    template_path = f"{template}.j2"
    with open(env.loader.get_source(env, template_path)[1]) as file:
        post = frontmatter.load(file)

    template = env.from_string(post.content)
    try:
        return template.render(**kwargs)
    except TemplateError as e:
        raise ValueError(f"Error rendering template: {str(e)}")
```

Step by step:

**1. Resolve the file path:**
```python
env.loader.get_source(env, template_path)[1]
```
`get_source()` returns a tuple `(source_string, filepath, uptodate_fn)`. `[1]` is just the file path. We use this to open the file directly so `python-frontmatter` can parse it.

**2. Load and split frontmatter from body:**
```python
post = frontmatter.load(file)
```
`python-frontmatter` reads the file, parses the YAML between the `---` markers into `post.metadata` (a dict), and puts everything after the second `---` into `post.content` (a plain string). So `post.content` is just the Jinja2 template text, with no frontmatter noise in it.

**3. Compile and render:**
```python
template = env.from_string(post.content)
return template.render(**kwargs)
```
`env.from_string()` compiles the template string. `.render(**kwargs)` substitutes all `{{ variable }}` placeholders with the values you passed in as keyword arguments. The rendered string (the final system prompt) is returned.

**Example call:**
```python
prompt = PromptManager.get_prompt(
    "ticket_analysis",
    name="Sofia",
    company="Acme Corp",
    pipeline="billing",
)
```
This returns the ticket_analysis template rendered with name='Sofia', topic='billing', and company_name='Acme Corp'. The {{ name | default('Emma') }} expression evaluates the name variable directly — since name is defined and passed in, the default('Emma') filter never fires and 'Emma' never appears in the output.

---

## Step 4 — `get_template_info()`: introspect a template

```python
@staticmethod
def get_template_info(template: str) -> dict:
    env = PromptManager._get_env()
    template_path = f"{template}.j2"
    with open(env.loader.get_source(env, template_path)[1]) as file:
        post = frontmatter.load(file)

    ast = env.parse(post.content)
    variables = meta.find_undeclared_variables(ast)

    return {
        "name": template,
        "description": post.metadata.get("description", "No description provided"),
        "author": post.metadata.get("author", "Unknown"),
        "variables": list(variables),
        "frontmatter": post.metadata,
    }
```

This is the introspection utility — it answers "what do I need to pass to render this template?" without actually rendering it.

The interesting part:
```python
ast = env.parse(post.content)
variables = meta.find_undeclared_variables(ast)
```

`env.parse()` compiles the template into an AST (abstract syntax tree) without rendering it. `meta.find_undeclared_variables()` walks that AST and returns the set of variable names that the template uses but doesn't declare internally — i.e., the variables you must pass in from outside.

For `ticket_analysis.j2`, this would return `{"name", "company", "pipeline"}`.

**Error handling:** both `get_prompt()` and `get_template_info()` raise `jinja2.exceptions.TemplateNotFound` when the template file does not exist (raised by `FileSystemLoader.get_source()`). Note: the source docstring says `FileNotFoundError`, but the actual exception raised is `TemplateNotFound` — callers doing exception handling should catch `jinja2.exceptions.TemplateNotFound`.

---

## Step 5 — How a node uses `PromptManager`

In the Customer Care workflow nodes, a node that needs a dynamic prompt calls `PromptManager.get_prompt()` inside `get_agent_config()`:

```python
# hypothetical pattern (cleaner than the current FilterSpamNode which hardcodes):
def get_agent_config(self) -> AgentConfig:
    prompt = PromptManager.get_prompt(
        "ticket_analysis",
        name="Emma",
        company="TechGear",
    )
    return AgentConfig(
        system_prompt=prompt,
        output_type=self.OutputType,
        deps_type=None,
        model_provider=ModelProvider.OPENAI,
        model_name="gpt-4o",
    )
```

The rendered prompt string goes directly into `AgentConfig.system_prompt`, which then goes into pydantic-ai's `Agent(system_prompt=...)`. The `.j2` file is the single source of truth for what the LLM is told.

---

## Mental model: templates as the prompt source of truth

```
app/prompts/ticket_analysis.j2
    ├── YAML frontmatter → post.metadata (description, author, ...)
    └── Jinja2 body → post.content → rendered with kwargs → system prompt string
```

The `.j2` file is to prompts what a Python module is to code — a versioned, editable, single source of truth. Changing it doesn't require a code change or a server restart. `get_template_info()` lets you discover what a template needs at runtime. `StrictUndefined` makes missing variables loud, not silent.
