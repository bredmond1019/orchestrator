from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

from core.nodes.base import Node
from core.schema import NodeConfig
from core.task import TaskContext


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
                future = executor.submit(node().process, task_context)
                future_list.append(future)

            results = [future.result() for future in future_list]
        return results

    @abstractmethod
    def process(self, task_context: TaskContext) -> TaskContext:
        pass
