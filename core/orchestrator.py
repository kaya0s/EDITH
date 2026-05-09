"""
Jarvis Core Orchestrator
========================

The central brain of the Jarvis platform.

Key design decisions
--------------------
* The orchestrator knows NOTHING about voice, LLMs, or any specific feature.
* Every feature is a ``BaseModule`` subclass registered at startup.
* New capabilities are added by registering a new module — zero changes to
  existing code (Open/Closed Principle).

Lifecycle of a module
---------------------
    register()  → on_load()  → run() [N times]  → on_unload()  → unregister()
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Base Module Contract
# ═══════════════════════════════════════════════════════════════════════════════


class BaseModule(ABC):
    """
    Abstract base class that every Jarvis module must implement.

    Subclass this and implement at minimum:
      * ``name``  — a unique lowercase identifier string.
      * ``run()`` — the module's primary action.

    The lifecycle hooks ``on_load`` / ``on_unload`` are optional but
    recommended for setup/teardown of resources.
    """

    # ── Required interface ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Globally unique, lowercase, hyphen-safe identifier.

        Examples: ``'voice'``, ``'automation'``, ``'memory'``
        """

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Execute the module's primary action and return its result.

        ``**kwargs`` are forwarded verbatim from ``Orchestrator.run()``,
        allowing each module to declare its own keyword arguments without
        changing the orchestrator signature.
        """

    # ── Optional lifecycle hooks ──────────────────────────────────────────────

    def on_load(self) -> None:
        """
        Called immediately after the module is registered.

        Override to acquire resources, validate config, or print a
        ready-message to the user.
        """

    def on_unload(self) -> None:
        """
        Called just before the module is deregistered.

        Override to release resources, flush buffers, or persist state.
        """

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<Module name={self.name!r} type={type(self).__name__}>"


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════


class Orchestrator:
    """
    Plug-and-play module manager for the Jarvis platform.

    The orchestrator is intentionally thin: it manages the module registry
    and routes execution — nothing more.  All feature logic lives in modules.

    Quick-start
    -----------
    >>> orch = Orchestrator()
    >>> orch.register(VoiceModule())
    >>> result = orch.run("voice")

    Chained registration
    --------------------
    >>> (
    ...     Orchestrator()
    ...     .register(VoiceModule())
    ...     .register(AutomationModule())
    ...     .register(MemoryModule())
    ... )
    """

    def __init__(self) -> None:
        self._registry: Dict[str, BaseModule] = {}
        logger.info("Jarvis Orchestrator initialised — ready to accept modules.")

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, module: BaseModule) -> "Orchestrator":
        """
        Register a module with the orchestrator.

        If a module with the same name is already registered it will be
        gracefully replaced: ``on_unload()`` is called on the old instance
        before the new one is stored and its ``on_load()`` is called.

        Returns *self* to support fluent / chained registration.

        Raises:
            TypeError: If *module* is not a ``BaseModule`` subclass instance.
        """
        if not isinstance(module, BaseModule):
            raise TypeError(
                f"Expected a BaseModule subclass instance, "
                f"got {type(module).__name__!r}."
            )

        if module.name in self._registry:
            logger.warning(
                "Module %r is already registered — replacing existing instance.",
                module.name,
            )
            self._registry[module.name].on_unload()

        self._registry[module.name] = module
        module.on_load()
        logger.info(
            "Module %r registered successfully.  Active modules: %s",
            module.name,
            self.modules,
        )
        return self  # enable fluent chaining

    def unregister(self, name: str) -> None:
        """
        Gracefully unregister a module by name.

        Calls ``on_unload()`` on the module before removing it.
        Logs a warning (rather than raising) if the name is not found,
        so callers don't need try/except for idempotent teardown.
        """
        module = self._registry.pop(name, None)
        if module is None:
            logger.warning(
                "Attempted to unregister unknown module %r.  Registered modules: %s",
                name,
                self.modules,
            )
            return
        module.on_unload()
        logger.info("Module %r unregistered.", name)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseModule]:
        """
        Return the module registered under *name*, or ``None``.

        Prefer this over direct registry access so call sites are not
        coupled to the internal dict structure.
        """
        return self._registry.get(name)

    def has(self, name: str) -> bool:
        """Return ``True`` if a module named *name* is currently registered."""
        return name in self._registry

    @property
    def modules(self) -> List[str]:
        """Return an alphabetically-sorted list of all registered module names."""
        return sorted(self._registry.keys())

    # ── Execution ─────────────────────────────────────────────────────────────

    def run(self, name: str, **kwargs) -> Any:
        """
        Route execution to a specific module and return its result.

        Args:
            name:     The registered module name (case-sensitive).
            **kwargs: Forwarded verbatim to ``module.run(**kwargs)``.

        Raises:
            KeyError: If no module with *name* is registered.
        """
        module = self._registry.get(name)
        if module is None:
            raise KeyError(
                f"Module {name!r} is not registered.  Available modules: {self.modules}"
            )
        logger.info("Dispatching to module %r.", name)
        return module.run(**kwargs)

    def run_all(self, **kwargs) -> Dict[str, Any]:
        """
        Run every registered module and collect their results.

        Individual failures are caught, logged with a full traceback, and
        stored as ``None`` in the result dict so one bad module cannot
        prevent the others from running.

        Args:
            **kwargs: Forwarded to every module's ``run()`` method.

        Returns:
            ``{module_name: result_or_None}`` for all registered modules.
        """
        results: Dict[str, Any] = {}
        for name, module in self._registry.items():
            try:
                logger.info("run_all → dispatching to module %r.", name)
                results[name] = module.run(**kwargs)
            except Exception as exc:
                logger.error(
                    "Module %r raised an unhandled error during run_all: %s",
                    name,
                    exc,
                    exc_info=True,
                )
                results[name] = None
        return results

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<Orchestrator modules={self.modules}>"

    def __len__(self) -> int:
        """Return the number of registered modules."""
        return len(self._registry)

    def __contains__(self, name: str) -> bool:
        """Support ``'voice' in orchestrator`` syntax."""
        return name in self._registry
