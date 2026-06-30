import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_tmp = tempfile.mkdtemp(prefix="invoice-auditor-test-")
os.environ.setdefault("DB_PATH", os.path.join(_tmp, "t.db"))

import pytest  # noqa: E402

from libs.common.logging import silence  # noqa: E402

silence()


@pytest.fixture(autouse=True)
def _state():
    from libs.common import rbac
    from services import bootstrap
    bootstrap.seed_all()          # resets + ingests + detects
    rbac.set_role("kyle-hq")      # role must not leak across tests
    yield
