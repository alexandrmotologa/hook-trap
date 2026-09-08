"""
Tunnel management facade providing backward-compatible interface.
Internally delegates to object-oriented TunnelManager and provider strategies.
"""

from hook_trap.services.tunnel import (
    BaseTunnelProvider,
    CloudflareTunnelProvider,
    NgrokTunnelProvider,
    TunnelManager,
    tunnel_manager,
)

__all__ = [
    "BaseTunnelProvider",
    "CloudflareTunnelProvider",
    "NgrokTunnelProvider",
    "TunnelManager",
    "tunnel_manager",
]
