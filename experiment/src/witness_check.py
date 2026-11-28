"""Witness replay checker (alias module).

`replay_identity(identity, y)` returns True iff the role->entity map `y` is an
admissible identity of the task (injective, inside unary domains, on anchors,
edge- and metric-preserving), as defined in Section 3 of the paper. It is the
function the reference builder and the scorer use; it lives in
coordination_confirmation_data.py under its historical name `legal`, which the
frozen records' design hashes pin, so this module only re-exports it.
"""
from coordination_confirmation_data import legal as replay_identity  # noqa: F401
