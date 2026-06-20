"""Blog-decision router for the content_pipeline workflow.

Routes to the blog branch (``BlogWriterNode``) only when the event's
``make_blog`` flag is true. When it is false there is no matching route and no
fallback, so ``BaseRouter.route`` returns ``None`` and the run terminates after
storage (the digest-only path). Follows the ``ticket_router_node.py`` shape.
"""

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext

from workflows.content_pipeline_workflow_nodes.blog_writer_node import BlogWriterNode


class BlogDecisionRouterNode(BaseRouter):
    """Router that gates the optional blog branch on ``event.make_blog``."""

    def __init__(self):
        self.routes = [MakeBlogRouter()]
        # No fallback: digest-only runs end here when make_blog is false.
        self.fallback = None


class MakeBlogRouter(RouterNode):
    """Routes to the blog writer when blog generation was requested."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        if task_context.event.make_blog:
            return BlogWriterNode()
        return None
