"""Canonical organization vocabulary over the existing mapped identity.

During the P0 compatibility period the physical tables and SQLAlchemy registry
names stay labs/Lab and lab_users/LabUser. These aliases are the SAME mapper,
not joined tables or copied entities. Historical public IDs remain unchanged.
"""

from .lab import Lab as Organization
from .lab import LabRole as OrganizationRole
from .lab import LabUser as OrganizationMember
from .lab import OrganizationType

__all__ = ["Organization", "OrganizationRole", "OrganizationMember", "OrganizationType"]
