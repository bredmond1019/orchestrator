"""ContentPipelineWorkflow — source-routed knowledge-feed pipeline (Project A).

Turns a YouTube or article URL into a categorized, embedded ``LearningArtifact``
plus a static-HTML personal digest (always), and — only when ``make_blog`` is
true — a self-corrected blog draft.

Graph::

    SourceRouterNode (router)
        -> FetchTranscriptNode | FetchArticleNode
            -> SummarizerNode
                -> StorageNode
                    -> BlogDecisionRouterNode (router)
                        -> BlogWriterNode -> SelfCriticNode -> ReviseNode
                            -> TranslatePtBrNode

The two routers are marked ``is_router=True``. ``BlogDecisionRouterNode`` routes
to the blog branch only when ``event.make_blog`` is true; otherwise the run ends
after ``StorageNode`` (digest-only). The whole graph is a DAG — the blog branch
is strictly linear (writer -> self-critic -> revise -> translate), no loop-back
— so ``WorkflowValidator`` passes. ``TranslatePtBrNode`` produces the pt-BR
translation of the finished post for the brand's PT+EN cadence. Persistence
stays injected inside ``StorageNode``; the workflow makes no deployment
decisions.
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.content_pipeline_schema import ContentPipelineEventSchema

from workflows.content_pipeline_workflow_nodes.blog_decision_router_node import (
    BlogDecisionRouterNode,
)
from workflows.content_pipeline_workflow_nodes.blog_writer_node import BlogWriterNode
from workflows.content_pipeline_workflow_nodes.fetch_article_node import (
    FetchArticleNode,
)
from workflows.content_pipeline_workflow_nodes.fetch_transcript_node import (
    FetchTranscriptNode,
)
from workflows.content_pipeline_workflow_nodes.revise_node import ReviseNode
from workflows.content_pipeline_workflow_nodes.self_critic_node import SelfCriticNode
from workflows.content_pipeline_workflow_nodes.source_router_node import (
    SourceRouterNode,
)
from workflows.content_pipeline_workflow_nodes.storage_node import StorageNode
from workflows.content_pipeline_workflow_nodes.summarizer_node import SummarizerNode
from workflows.content_pipeline_workflow_nodes.translate_ptbr_node import (
    TranslatePtBrNode,
)


class ContentPipelineWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description=(
            "Source-routed content pipeline: fetch (transcript or article) -> "
            "summarize -> embed + persist + render digest -> optional blog branch."
        ),
        event_schema=ContentPipelineEventSchema,
        start=SourceRouterNode,
        nodes=[
            NodeConfig(
                node=SourceRouterNode,
                connections=[FetchTranscriptNode, FetchArticleNode],
                description="Classify the URL and route to the matching fetch node.",
                is_router=True,
            ),
            NodeConfig(
                node=FetchTranscriptNode,
                connections=[SummarizerNode],
                description="Fetch a YouTube transcript for the event URL.",
            ),
            NodeConfig(
                node=FetchArticleNode,
                connections=[SummarizerNode],
                description="Extract readable article text for the event URL.",
            ),
            NodeConfig(
                node=SummarizerNode,
                connections=[StorageNode],
                description="Summarize the fetched text into a structured SummaryOutput.",
            ),
            NodeConfig(
                node=StorageNode,
                connections=[BlogDecisionRouterNode],
                description="Embed at write time, persist the artifact, render the digest.",
            ),
            NodeConfig(
                node=BlogDecisionRouterNode,
                connections=[BlogWriterNode],
                description="Route to the blog branch only when make_blog is true.",
                is_router=True,
            ),
            NodeConfig(
                node=BlogWriterNode,
                connections=[SelfCriticNode],
                description="Draft a blog post in Brandon's voice from the summary.",
            ),
            NodeConfig(
                node=SelfCriticNode,
                connections=[ReviseNode],
                description="Critique the draft for clarity, accuracy, and voice.",
            ),
            NodeConfig(
                node=ReviseNode,
                connections=[TranslatePtBrNode],
                description="Apply the critique and produce the revised English post.",
            ),
            NodeConfig(
                node=TranslatePtBrNode,
                connections=[],
                description="Translate the finished post into pt-BR (terminal).",
            ),
        ],
    )
