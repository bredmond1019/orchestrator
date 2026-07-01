from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

from core.nodes.base import Node
from core.schema import NodeConfig
from core.task import NodeStatus, TaskContext


class ParallelNode(Node, ABC):
    """
    Represents a node capable of executing other nodes in parallel.

    This abstract class serves as the base class for implementing nodes
    that process tasks concurrently using multithreading. Subclasses
    must implement the `process` method to define specific processing
    logic.
    """

    def execute_nodes_in_parallel(self, task_context: TaskContext):
        node_config: NodeConfig = task_context.metadata["nodes"][self.__class__]
        future_list = []
        with ThreadPoolExecutor() as executor:
            for node in node_config.parallel_nodes:
                cloned_context = task_context.model_copy(deep=True)
                future = executor.submit(node().process, cloned_context)
                future_list.append(future)

            results = [future.result() for future in future_list]

        for result_context in results:
            for node_name, output in result_context.nodes.items():
                if node_name not in task_context.nodes:
                    task_context.nodes[node_name] = output
                else:
                    task_context.nodes[node_name].update(output)

            for node_name, run in result_context.node_runs.items():
                existing_run = task_context.node_runs.get(node_name)
                should_update = (node_name not in task_context.node_runs or
                                existing_run.status == NodeStatus.PENDING)
                if should_update:
                    task_context.node_runs[node_name] = run

        return results

    @abstractmethod
    def process(self, task_context: TaskContext) -> TaskContext:
        pass
