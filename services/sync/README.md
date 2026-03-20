# Sync Service

Handle optional upstream synchronization without becoming part of the mission-critical path.

Design rule:
- queue locally, retry safely, and degrade gracefully when remote systems are unavailable

