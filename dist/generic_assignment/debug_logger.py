import logging
_logger = logging.getLogger(__name__)


class DebugLogger(list):
    def __init__(self, *args, **kwargs):
        super(DebugLogger, self).__init__(*args, **kwargs)
        self._format_str = (
            "{index: <4}|{rule.name}[{rule.id}]"
            "({rule.assign_type})({rule.policy_id.name}) "
            "obj({obj._name})[{obj.id}] {obj.display_name}: {msg}")
        self._format_html_row = (
            "<tr>"
            "<th>{index}</th>"
            "<td>{rule.name}</td><td>{rule.id}</td>"
            "<td>{rule.assign_type}</td><td>{rule.policy_id.name}</td>"
            "<td>{obj._name}</td><td>{obj.id}</td><td>{obj.display_name}</td>"
            "<td>{msg}</td>"
            "</tr>"
        )
        self._format_html_header = (
            "<tr>"
            "<th rowspan='2'>Index</th>"
            "<th colspan='4'>Rule</th>"
            "<th colspan='3'>Object</th>"
            "<th rowspan='2'>Message</th>"
            "</tr>"
            "<tr>"
            "<th>Name</th><th>ID</th><th>Type</th><th>Policy</th>"
            "<th>Model</th><th>ID</th><th>Name</th>"
            "</tr"
        )
        self._index = 1

    def format_str(self, index, rule, obj, msg):
        return self._format_str.format(
            index=index, rule=rule, obj=obj, msg=msg)

    def format_html(self, index, rule, obj, msg):
        return self._format_html_row.format(
            index=index, rule=rule, obj=obj, msg=msg)

    def log(self, rule, obj, msg):
        self.append((self._index, rule, obj, msg))
        _logger.info(self.format_str(self._index, rule, obj, msg))
        self._index += 1

    def get_log_html(self):
        body = "".join(
            self.format_html(index, rule, obj, msg)
            for index, rule, obj, msg in self)
        table_classes = "table table-bordered table-condensed table-striped"
        return (
            "<table class='%(table_classes)s'>%(header)s%(body)s</table>"
        ) % {
            'header': self._format_html_header,
            'body': body,
            'table_classes': table_classes,
        }
