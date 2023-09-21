import re


class EventHandlerPath:
    def __init__(self, source_model, target_model, target_path):
        self._source_model = source_model
        self._target_model = target_model
        self._target_path = target_path

    @property
    def source_model(self):
        return self._source_model

    @property
    def target_model(self):
        return self._target_model

    @property
    def target_path(self):
        return self._target_path

    def _find_targets__self(self, source_record):
        """ Simple case, when target is same as source record.
        """
        return source_record

    def _find_targets__delegation_implementation(self, source_record):
        """ This is special case when event source is Interface
            (inherits generic.mixin.delegation.interface)
            and target (handler) model is Implementation of that interface.
            So, in this case we are already have enough data to find the
            way to reach implementation model from event source (interface)
        """
        implementation_model = source_record[
            source_record._generic_mixin_implementation_model_field
        ]
        if implementation_model != self._target_model:
            # Interface's implementation has different model,
            # then expected by this handler. Thus return empty recordset
            return source_record.env[self._target_model].browse()

        # Normally, target of this handler is implementation
        # of source's interface
        return source_record.env[implementation_model].browse(
            source_record[
                source_record._generic_mixin_implementation_id_field
            ]
        )

    def _find_targets__generic_m2o(self, source_record):
        """ Find targets specified by generic many2one field on source record.

            In this case, target is specified by 2 fields:
            - model
            - res_id

            So, we have to try to find target record (if target model matches
            handler's model).

            :param recordset source_record: record that triggered event
        """
        # TODO: Make parsing as cached property to improve performance
        m = re.match(
            r"^generic-m2o:(?P<model>\w+):(?P<res_id>\w+)$",
            self._target_path)
        if not m:
            return source_record.env[self._target_model].browse()
        gm2o_model = source_record[m.group('model')]
        gm2o_res_id = source_record[m.group('res_id')]
        if not (gm2o_model and gm2o_res_id):
            # No data for generic m2o field. Thus return empty recordset
            return source_record.env[self._target_model].browse()
        if gm2o_model != self._target_model:
            # Generic many2one model does not match target model,
            # thus return empty recordset
            return source_record.env[self._target_model].browse()
        # Return recordset with record pointed by generic m2o field
        # on source record.
        return source_record.env[gm2o_model].browse(gm2o_res_id)

    def _find_targets__default(self, source_record):
        """ Default implementation of find targets.

            Simply call source's `mapped` method to find target records.
        """
        return source_record.mapped(self._target_path)

    def find_targets(self, source_record):
        """ Find target records to run handler on
        """
        if source_record._name != self._source_model:
            raise ValueError(
                "Cannot find targets for %s. Wrong model" % source_record._name
            )

        if self._target_path == 'self':
            return self._find_targets__self(source_record)
        if self._target_path == 'delegation:interface-to-implementation':
            return self._find_targets__delegation_implementation(source_record)
        if self._target_path.startswith('generic-m2o:'):
            return self._find_targets__generic_m2o(source_record)

        return self._find_targets__default(source_record)
