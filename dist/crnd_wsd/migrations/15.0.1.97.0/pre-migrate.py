from odoo.addons.generic_mixin.tools.migration_utils import (
    ensure_version,
    cleanup_module_data,
    migrate_xmlids_to_module
)


@ensure_version('1.97.0')
def migrate(cr, installed_version):
    migrate_xmlids_to_module(cr,
                             src_module='crnd_wsd_priority',
                             dst_module='crnd_wsd',
                             models=['ir.model.fields'])

    # Cleanup module data
    cleanup_module_data(cr, 'crnd_wsd_priority')
