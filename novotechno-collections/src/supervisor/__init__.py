"""
NovotEcho Collections Supervisor

A monitoring and coordination system for NovotEcho collections agents.
Provides health checking, dashboard generation, and state consistency validation.
"""

from .health_checker import HealthChecker, AgentHealthStatus, StateConsistencyChecker
from .dashboard import Dashboard, MetricsCollector

__version__ = "1.0.0"
__all__ = [
    "HealthChecker",
    "AgentHealthStatus", 
    "StateConsistencyChecker",
    "Dashboard",
    "MetricsCollector"
]
