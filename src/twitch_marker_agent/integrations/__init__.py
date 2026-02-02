"""
Integrations package for Twitch Marker Agent.

Contains integration adapters for external systems like:
- Streamer.bot triggers
- Future: webhooks, Discord bots, etc.

These integrations call into core/ modules and MUST NOT
contain business logic themselves.
"""

__all__ = [
    "streamerbot_trigger",
]
