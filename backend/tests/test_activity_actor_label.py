"""Actor labelling for Activity History (pure; no database)."""

import uuid

from app.services.analytics_service import (
    SYSTEM_OTHER_LABEL,
    SYSTEM_SETUP_LABEL,
    UNKNOWN_USER_LABEL,
    actor_label,
)


def test_bootstrap_inserts_without_actor_are_initial_setup() -> None:
    assert actor_label(None, None, "branches", "INSERT") == (SYSTEM_SETUP_LABEL, "System")
    assert actor_label(None, None, "profiles", "INSERT") == (SYSTEM_SETUP_LABEL, "System")


def test_other_actorless_changes_are_plain_system_not_initial_setup() -> None:
    assert actor_label(None, None, "profiles", "UPDATE") == (SYSTEM_OTHER_LABEL, "System")
    assert actor_label(None, None, "orders", "INSERT") == (SYSTEM_OTHER_LABEL, "System")


def test_signed_in_users_show_their_name_never_system() -> None:
    uid = uuid.uuid4()
    assert actor_label(uid, "Satwa Manager", "orders", "INSERT") == ("Satwa Manager", "User")
    # An actor id with no matching profile is never disguised as System.
    assert actor_label(uid, None, "orders", "INSERT") == (UNKNOWN_USER_LABEL, "User")
