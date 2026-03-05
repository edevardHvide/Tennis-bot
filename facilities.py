"""
Tennis Facilities Configuration

This module contains facility IDs for the Matchi booking system.

Facilities are split into two categories:
- Active: Currently monitored for available courts
- Inactive: Temporarily disabled (e.g., winter closures, maintenance)

To temporarily disable a facility (e.g., for winter):
1. Move the entry from 'facilities' to 'inactive_facilities'
2. Add a comment explaining why (e.g., "Winter closure")

To re-enable a facility:
1. Move the entry from 'inactive_facilities' back to 'facilities'
2. Remove or update the comment
"""

# Active facilities that are currently monitored
facilities = {
    "frogner": 2259,
    "ota": 1779,
    "bergentennisarena": 301,
}

# Inactive facilities (e.g., winter closures, maintenance)
# These are preserved for reference but not monitored
inactive_facilities = {
    "voldsløkka": 642,  # Winter closure (vinterstengt)
}
