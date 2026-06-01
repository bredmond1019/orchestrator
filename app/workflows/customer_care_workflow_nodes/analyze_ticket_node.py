from core.nodes.parallel import ParallelNode
from core.task import TaskContext


class AnalyzeTicketNode(ParallelNode):
    def process(self, task_context: TaskContext) -> TaskContext:
        self.execute_nodes_in_parallel(task_context)
        return task_context
