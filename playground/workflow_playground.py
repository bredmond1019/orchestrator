import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "app"))
sys.path.append(str(project_root))

from playground.utils.event_loader import EventLoader
from workflows.customer_care_workflow import CustomerCareWorkflow

import nest_asyncio
nest_asyncio.apply()

"""
This playground is used to test the WorkflowRegistry and the workflows themselves.
"""

event = EventLoader.load_event(event_key="product")
workflow = CustomerCareWorkflow()
result = workflow.run(event)
print(result)
