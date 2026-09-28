# PB-4 (domain): S-1 trust gate enforcement via __call__()
# Verifies that every concrete BaseNode subclass under src/nodes/ actually
# rejects a caller below its required_trust_level. Calling node.execute(state)
# directly bypasses __call__() entirely and never exercises the S-1 gate, so
# this test goes through __call__() specifically.

import importlib
import inspect
import pkgutil

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel


def _discover_node_classes() -> list[type]:
    from framework.nodes.base_node import BaseNode

    pkg = importlib.import_module("src.nodes")
    discovered = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="src.nodes."):
        module = importlib.import_module(modname)
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseNode)
                and attr is not BaseNode
                and attr.__module__ == modname
                and not inspect.isabstract(attr)
            ):
                discovered.append(attr)
    return discovered


class TestS1TrustGate:
    """PB-4: __call__() must reject a caller below required_trust_level.

    Fixed baseline (not the node's own declared value): every domain node
    in this template is required by config/agent.yaml's manifest-level
    `required_trust_level: VERIFIED_EXTERNAL` to reject ANONYMOUS callers.
    Asserting against the node's own `required_trust_level` attribute would
    let a regression to ANONYMOUS pass silently (the check would just skip
    itself) — this test asserts against the fixed manifest expectation
    instead, so it fails loudly if a node ever regresses to ANONYMOUS.
    """

    def test_anonymous_caller_rejected_by_every_node(self):
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        failures: list[str] = []
        for node_cls in node_classes:
            assert node_cls.required_trust_level != TrustLevel.ANONYMOUS, (
                f"{node_cls.__name__}: required_trust_level regressed to ANONYMOUS "
                f"— config/agent.yaml declares VERIFIED_EXTERNAL at the manifest "
                f"level; every domain node must match or exceed it"
            )

            instance = node_cls()
            state = {
                "caller_trust_level": TrustLevel.ANONYMOUS.value,
                "correlation_id": "pb4-s1-trust-gate-test",
            }
            result = instance(state)  # __call__(), not execute() — exercises S-1

            if result.get("status") != AgentStatus.ERROR.value:
                failures.append(
                    f"{node_cls.__name__}: ANONYMOUS caller was not rejected "
                    f"(required_trust_level={node_cls.required_trust_level}); "
                    f"got status={result.get('status')!r}"
                )

        assert not failures, "\n\n".join(failures)

    def test_sufficiently_trusted_caller_is_not_rejected_by_s1(self):
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        failures: list[str] = []
        for node_cls in node_classes:
            instance = node_cls()
            state = {
                "caller_trust_level": node_cls.required_trust_level.value,
                "correlation_id": "pb4-s1-trust-gate-test",
            }
            result = instance(state)

            # Node-specific business logic may still fail on this minimal
            # state (e.g. missing chunks/raw_questions) — that is expected
            # and orthogonal to S-1. What must NOT happen is rejection at
            # the trust-gate stage specifically.
            if result.get("status") == AgentStatus.ERROR.value and any(
                "trust gate" in msg.lower() for msg in result.get("error_log", [])
            ):
                failures.append(
                    f"{node_cls.__name__}: caller at required_trust_level was "
                    f"incorrectly rejected by the S-1 trust gate"
                )

        assert not failures, "\n\n".join(failures)
