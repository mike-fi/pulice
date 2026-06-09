"""Allow running the admin TUI with: python -m pulice.admin"""

import sys
from pulice.admin.app import PuliceAdmin

state_dir = sys.argv[1] if len(sys.argv) > 1 else None
app = PuliceAdmin(state_dir=state_dir)
app.run()
