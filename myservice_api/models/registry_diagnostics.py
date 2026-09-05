"""Runtime guard for constraints Odoo 19 silently refuses to create.

`tests/test_source_guards.py` parses our own modules' source, which is the
right tool for code we control. It deliberately does not cover the vendored
trees (`crnd-19/`, `oca-19/`), because an upstream refresh can reintroduce the
pattern in code no source test of ours is watching — and the whole failure
mode here is that nothing complains.

This closes that half at runtime. It asks the built registry the same question
`odoo/orm/model_classes.py:162` asks — does this model class still carry a
`_sql_constraints` attribute? — and reports the model NAMES rather than a
count, so the answer is actionable rather than merely alarming.

It logs at ERROR and does not raise. A raise here would take the registry
down for every tenant on a pod whose liveness probe hits `/web/login`, i.e. a
full outage, in response to a constraint that was in the worst case already
silently absent. The detection belongs in CI (`.github/workflows/ci.yml`) and
in an asserted diagnostic, not in a kill switch.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

_WARNING = (
    "Model attribute '_sql_constraints' is no longer supported on Odoo 19 — "
    "these models declare constraints the ORM silently does NOT create: %s. "
    "Use models.Constraint(\"UNIQUE (...)\", \"message\") instead. "
    "See docs/constraint-audit.md."
)


def dead_sql_constraint_models(env):
    """Names of registry models still declaring `_sql_constraints`.

    Odoo 19's `BaseModel` no longer defines the attribute, so a plain
    `hasattr` reproduces exactly what the ORM's own warning tests. Checked on
    the model classes rather than the registry object, which legitimately
    carries an unrelated `_sql_constraints` set of its own.
    """
    return sorted(
        name for name, cls in env.registry.items()
        if hasattr(cls, "_sql_constraints")
    )


class RegistryDiagnostics(models.AbstractModel):
    _name = "myservice.api.registry.diagnostics"
    _description = "Cadra API registry diagnostics"

    def _register_hook(self):
        """Runs once per registry load, after every module is in place.

        That timing is what makes it able to see the vendored trees: by this
        point `crnd-19/` and `oca-19/` are loaded like any other addon.
        """
        result = super()._register_hook()
        offenders = dead_sql_constraint_models(self.env)
        if offenders:
            _logger.error(_WARNING, ", ".join(offenders))
        return result

    @api.model
    def collect(self):
        """The diagnostic payload behind `GET /api/v1/meta/diagnostics`."""
        offenders = dead_sql_constraint_models(self.env)
        return {
            "dead_sql_constraints": {
                "count": len(offenders),
                "models": offenders,
                "detail": ("Constraints declared with `_sql_constraints` are "
                           "silently not created on Odoo 19."),
            },
        }
