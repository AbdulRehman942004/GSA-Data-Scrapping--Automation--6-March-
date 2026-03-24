"""
Shared automation state.

All route modules import from here to read/write the running flags and
hold references to the active automation objects.
"""
import threading

state_lock = threading.Lock()

is_link_generation_running: bool = False
is_scraping_running: bool = False

active_link_automation = None
active_scraping_automation = None

# Parallel scraping
parallel_orchestrator = None
