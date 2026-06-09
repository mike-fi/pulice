"""Admin TUI screens."""

from pulice.admin.screens.dashboard import DashboardScreen
from pulice.admin.screens.stacks import StacksScreen
from pulice.admin.screens.system import SystemScreen
from pulice.admin.screens.tasks import TasksScreen
from pulice.admin.screens.tenants import TenantsScreen

__all__ = [
    'DashboardScreen',
    'TenantsScreen',
    'StacksScreen',
    'TasksScreen',
    'SystemScreen',
]
