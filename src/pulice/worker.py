"""Pulice task worker entry point.

Start with: ``huey_consumer pulice.worker.huey -w 2 -k process``
"""

from pulice.core.tasks import create_huey_instance

# The Huey instance must be module-level for the consumer to discover it.
huey = create_huey_instance()

# Import task definitions so they register with the huey instance.
import pulice.core.task_definitions  # noqa: F401, E402
