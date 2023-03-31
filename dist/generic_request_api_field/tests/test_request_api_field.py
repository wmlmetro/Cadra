import logging

from odoo.addons.generic_request_api.tests.test_api_endpoint_base import (
    TestApiEndpointsBase
)
from odoo.addons.generic_mixin.tests.common import deactivate_records_for_model

_logger = logging.getLogger(__name__)


class TestRequestApiEndpointField(TestApiEndpointsBase):

    def setUp(self):
        super(TestRequestApiEndpointField, self).setUp()

        self.create_vm_endpoint = self.env.ref(
            'generic_request_api_field.test_api_internal_endpoint_create_vm')
        self.rest_api_create_vm_endpoint = self.env.ref(
            'generic_request_api_field.test_rest_api_endpoint_create_vm')
        self.request_type_field = self.env.ref(
            'generic_request_field.request_type_field')

        deactivate_records_for_model(self.env, 'ir.rule')

    def test_internal_api_field(self):
        field_memory = self.env.ref(
            'generic_request_api_field.test_api_field_memory')
        field_cpu = self.env.ref(
            'generic_request_api_field.test_api_field_cpu')
        field_hdd = self.env.ref(
            'generic_request_api_field.test_api_field_hdd')
        field_os = self.env.ref(
            'generic_request_api_field.test_api_field_os')

        # Make CPU field not required for this test
        field_cpu.field_id.write({'mandatory': False})
        field_hdd.field_id.write({'mandatory': False})

        # Call API itself
        internal_request = self.call_api(self.create_vm_endpoint.url)

        self.assertEqual(field_memory.default_value, '1GB')
        self.assertFalse(field_cpu.default_value)
        self.assertFalse(field_hdd.default_value)
        self.assertEqual(field_os.default_value, 'ubuntu')

        self.assertEqual(len(internal_request.type_id.field_ids), 5)
        self.assertEqual(len(internal_request.value_ids), 5)
        self.assertEqual(
            internal_request.get_fields_data(),
            {
                'cpu': False,
                'memory': '1GB',
                'comment': '',
                'hdd': False,
                'os': 'ubuntu',
            })

    def test_internal_api_field_with_data(self):
        internal_request = self.call_api(
            self.create_vm_endpoint.url,
            params={
                'test_cpu_field': '4 Core',
                'test_hdd_field': '10GB',
                'test_mem_field': '2GB',
            })

        field_memory = self.env.ref(
            'generic_request_api_field.test_api_field_memory')
        field_cpu = self.env.ref(
            'generic_request_api_field.test_api_field_cpu')
        field_hdd = self.env.ref(
            'generic_request_api_field.test_api_field_hdd')
        field_os = self.env.ref(
            'generic_request_api_field.test_api_field_os')

        self.assertEqual(field_memory.default_value, '1GB')
        self.assertFalse(field_cpu.default_value)
        self.assertFalse(field_hdd.default_value)
        self.assertEqual(field_os.default_value, 'ubuntu')

        self.assertEqual(internal_request.get_field_value('memory'), '2GB')
        self.assertEqual(len(internal_request.type_id.field_ids), 5)
        self.assertEqual(len(internal_request.value_ids), 5)
        self.assertEqual(
            internal_request.get_fields_data(),
            {
                'cpu': '4 Core',
                'memory': '2GB',
                'comment': '',
                'hdd': '10GB',
                'os': 'ubuntu',
            })

    def test_rest_api_endpoint_controllers_no_fields(self):
        # pylint: disable=too-many-statements
        # Check the request type no have additional fields from
        # module generic_request_fields.
        creation_template = self.rest_api_endpoint.request_creation_template_id
        self.assertFalse(len(creation_template.request_type_id.field_ids))

        email_without_partner = "not_an_exising@email"
        post_data_json = {
            "author": {
                "email": email_without_partner
            },
        }

        requests_before = self.Request.search([])

        # TODO: maybe need use login 'Public user' pass 'public'?
        # user='Public user', password='public',
        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        post_response_json = {
            "request": {
                "name": request_new.name,
                "stage": {"name": "New", "code": "new", "is_closed": False},
                "type": {
                    "name": self.request_type.name,  # "API Type",
                    "code": self.request_type.code   # "T1"
                }
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>Test Rest API endpoint</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 0)
        self.assertEqual(len(request_new.value_ids), 0)

        # GET request by Request ID
        get_url_by_id = '%s/%s' % (self.rest_api_endpoint.url, request_new.id)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json = {
            "request": {
                "name": request_new.name,
                "author": {
                    "name": False,
                    "email": email_without_partner
                },
                "stage": {
                    "name": "New",
                    "code": "new",
                    "is_closed": False
                },
                "type": {
                    "name": request_new.type_id.name,
                    "code": request_new.type_id.code
                },
                "request_text": "<p>Test Rest API endpoint</p>",
                "response_text": False
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)

        # GET request by Request name
        get_url_by_name = '%s/%s' % (
            self.rest_api_endpoint.url, request_new.name)

        response = self.opener.get(
            self._get_test_url(get_url_by_name),
            headers={'Content-Type': 'application/json'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)

        put_data_json = {
            "request_text": "This text added to request by ID",
        }

        # PUT request by Request ID
        put_url_by_id = '%s/%s' % (self.rest_api_endpoint.url, request_new.id)

        response = self.opener.put(
            self._get_test_url(put_url_by_id),
            json=put_data_json)

        put_response_json = {
            "request": {
                "name": request_new.name,
                "stage": {
                    "name": "New",
                    "code": "new",
                    "is_closed": False
                },
                "type": {
                    "name": request_new.type_id.name,
                    "code": request_new.type_id.code
                },
            }
        }

        self.env.cache.invalidate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), put_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by ID</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 0)
        self.assertEqual(len(request_new.value_ids), 0)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json['request']['request_text'] = (
            '<p>This text added to request by ID</p>')

        # Check GET method
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by ID</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 0)
        self.assertEqual(len(request_new.value_ids), 0)

        put_data_json = {
            "request_text": "This text added to request by Name",
        }

        # PUT request by Request Name
        put_url_by_name = '%s/%s' % (
            self.rest_api_endpoint.url, request_new.name)

        response = self.opener.put(
            self._get_test_url(put_url_by_name),
            json=put_data_json)

        self.env.cache.invalidate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), put_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by Name</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 0)
        self.assertEqual(len(request_new.value_ids), 0)

        response = self.opener.get(
            self._get_test_url(get_url_by_name),
            headers={'Content-Type': 'application/json'})

        get_response_json['request']['request_text'] = (
            '<p>This text added to request by Name</p>')

        # Check GET method
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by Name</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 0)
        self.assertEqual(len(request_new.value_ids), 0)

    def test_rest_api_endpoint_controllers_post(self):
        # Check the request type no have additional fields from
        # module generic_request_fields.
        creation_template = (
            self.rest_api_create_vm_endpoint.request_creation_template_id)
        self.assertEqual(len(self.request_type_field.field_ids), 5)
        self.assertEqual(len(creation_template.request_type_id.field_ids), 5)
        self.assertEqual(
            len(self.request_type_field.field_ids),
            len(creation_template.request_type_id.field_ids))

        email_without_partner = "not_an_exising@email"
        post_data_json = {
            "author": {
                "email": email_without_partner
            },
            "data": {
                'cpu': '4 Cores',
            }
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_create_vm_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        post_response_json = {
            "request": {
                "name": request_new.name,
                "stage": {"name": "New", "code": "new", "is_closed": False},
                "type": {
                    "name": self.request_type_field.name,  # "Create VM",
                    "code": self.request_type_field.code   # "create_vm"
                },
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>create virtual machine</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        # Fields filled by default values
        self.assertEqual(request_new.get_field_value('cpu'), '4 Cores')
        self.assertEqual(request_new.get_field_value('memory'), '4 GB')
        self.assertFalse(request_new.get_field_value('comment'))
        self.assertEqual(request_new.get_field_value('hdd'), '30 GB')
        self.assertFalse(request_new.get_field_value('os'))

        # GET request by Request ID
        get_url_by_id = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.id)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json = {
            "request": {
                "name": request_new.name,
                "author": {
                    "name": False,
                    "email": email_without_partner
                },
                "stage": {
                    "name": "New",
                    "code": "new",
                    "is_closed": False
                },
                "type": {
                    "name": request_new.type_id.name,
                    "code": request_new.type_id.code
                },
                "request_text": "<p>create virtual machine</p>",
                "response_text": False,
                "data": {
                    "cpu": request_new.get_field_value('cpu'),  # "4 Cores"
                    "memory": request_new.get_field_value('memory'),  # "4 GB"
                    "comment": request_new.get_field_value('comment'),  # False
                    "hdd": request_new.get_field_value('hdd'),  # "30 GB"
                    "os": request_new.get_field_value('os')  # False
                }
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)

    def test_rest_api_endpoint_controllers_post_fields(self):
        # Check the request type no have additional fields from
        # module generic_request_fields.
        creation_template = (
            self.rest_api_create_vm_endpoint.request_creation_template_id)
        self.assertEqual(len(self.request_type_field.field_ids), 5)
        self.assertEqual(len(creation_template.request_type_id.field_ids), 5)
        self.assertEqual(
            len(self.request_type_field.field_ids),
            len(creation_template.request_type_id.field_ids))

        email_without_partner = "not_an_exising@email"
        post_data_json = {
            "author": {
                "email": email_without_partner
            },
            "data": {
                "cpu": "2 core",
                "memory": "6 GB",
                "comment": "Comment added from API by Post"
            }
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_create_vm_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        post_response_json = {
            "request": {
                "name": request_new.name,
                "stage": {"name": "New", "code": "new", "is_closed": False},
                "type": {
                    "name": self.request_type_field.name,  # "Create VM",
                    "code": self.request_type_field.code   # "create_vm"
                }
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>create virtual machine</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        self.assertEqual(request_new.get_field_value('cpu'), '2 core')
        self.assertEqual(request_new.get_field_value('memory'), '6 GB')
        self.assertEqual(
            request_new.get_field_value('comment'),
            'Comment added from API by Post')
        self.assertEqual(request_new.get_field_value('hdd'), '30 GB')
        self.assertFalse(request_new.get_field_value('os'))

        # GET request by Request ID
        get_url_by_id = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.id)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json = {
            "request": {
                "name": request_new.name,
                "author": {
                    "name": False,
                    "email": email_without_partner
                },
                "stage": {
                    "name": "New",
                    "code": "new",
                    "is_closed": False
                },
                "type": {
                    "name": request_new.type_id.name,
                    "code": request_new.type_id.code
                },
                "request_text": "<p>create virtual machine</p>",
                "response_text": False,
                "data": {
                    "cpu": request_new.get_field_value('cpu'),  # 2 Core
                    "memory": request_new.get_field_value('memory'),  # "6 GB"
                    "comment": request_new.get_field_value('comment'),  # False
                    "hdd": request_new.get_field_value('hdd'),  # "30 GB"
                    "os": request_new.get_field_value('os')  # False
                }
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)

    def test_rest_api_endpoint_controllers_put_fields(self):
        # pylint: disable=too-many-statements
        # Check the request type no have additional fields from
        # module generic_request_fields.
        creation_template = (
            self.rest_api_create_vm_endpoint.request_creation_template_id)
        self.assertEqual(len(self.request_type_field.field_ids), 5)
        self.assertEqual(len(creation_template.request_type_id.field_ids), 5)
        self.assertEqual(
            len(self.request_type_field.field_ids),
            len(creation_template.request_type_id.field_ids))

        email_without_partner = "not_an_exising@email"
        post_data_json = {
            "author": {
                "email": email_without_partner
            },
            "data": {
                "cpu": "2 core",
            }
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_create_vm_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        post_response_json = {
            "request": {
                "name": request_new.name,
                "stage": {"name": "New", "code": "new", "is_closed": False},
                "type": {
                    "name": self.request_type_field.name,  # "Create VM",
                    "code": self.request_type_field.code   # "create_vm"
                }
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>create virtual machine</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        self.assertEqual(request_new.get_field_value('cpu'), '2 core')
        self.assertEqual(request_new.get_field_value('memory'), '4 GB')
        self.assertFalse(request_new.get_field_value('comment'))
        self.assertEqual(request_new.get_field_value('hdd'), '30 GB')
        self.assertFalse(request_new.get_field_value('os'))

        # GET request by Request ID
        get_url_by_id = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.id)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json = {
            "request": {
                "name": request_new.name,
                "author": {
                    "name": False,
                    "email": email_without_partner
                },
                "stage": {
                    "name": "New",
                    "code": "new",
                    "is_closed": False
                },
                "type": {
                    "name": request_new.type_id.name,
                    "code": request_new.type_id.code
                },
                "request_text": "<p>create virtual machine</p>",
                "response_text": False,
                "data": {
                    "cpu": request_new.get_field_value('cpu'),  # False
                    "memory": request_new.get_field_value('memory'),  # "4 GB"
                    "comment": request_new.get_field_value('comment'),  # False
                    "hdd": request_new.get_field_value('hdd'),  # "30 GB"
                    "os": request_new.get_field_value('os')  # False
                }
            }
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)

        # GET request by Request name
        get_url_by_name = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.name)

        response = self.opener.get(
            self._get_test_url(get_url_by_name),
            headers={'Content-Type': 'application/json'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)

        put_data_json = {
            "request_text": "This text added to request by ID",
            "data": {
                "cpu": "4 core",
                "memory": "8 GB",
                "comment": "Comment added from API"
            }
        }

        # PUT request by Request ID
        put_url_by_id = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.id)

        response = self.opener.put(
            self._get_test_url(put_url_by_id),
            json=put_data_json)

        put_response_json = {
            "request": {
                "name": request_new.name,
                "stage": {
                    "name": "New",
                    "code": "new",
                    "is_closed": False
                },
                "type": {
                    "name": request_new.type_id.name,
                    "code": request_new.type_id.code
                },
            }
        }

        self.env.cache.invalidate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), put_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by ID</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json['request']['request_text'] = (
            '<p>This text added to request by ID</p>')

        get_response_json['request']['data'].update({
            "cpu": "4 core",
            "memory": "8 GB",
            "comment": "Comment added from API"
        })

        # Check GET method
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by ID</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        put_data_json = {
            "request_text": "This text added to request by Name",
            "data": {
                "cpu": "8 core",
                "memory": "16 GB",
                "comment": "Comment added from API by Name"
            }
        }

        # PUT request by Request Name
        put_url_by_name = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.name)

        response = self.opener.put(
            self._get_test_url(put_url_by_name),
            json=put_data_json)

        self.env.cache.invalidate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), put_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by Name</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        response = self.opener.get(
            self._get_test_url(get_url_by_name),
            headers={'Content-Type': 'application/json'})

        get_response_json['request']['request_text'] = (
            '<p>This text added to request by Name</p>')

        get_response_json['request']['data'].update({
            "cpu": "8 core",
            "memory": "16 GB",
            "comment": "Comment added from API by Name"
        })

        # Check GET method
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by Name</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        put_data_json = {
            "request_text": "This text added to request by ID",
            "data": {
                "cpu": "4 core",
                "memory": "8 GB",
                "comment": False,
            }
        }

        # PUT request by Request ID
        put_url_by_id = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.id)

        response = self.opener.put(
            self._get_test_url(put_url_by_id),
            json=put_data_json)

        self.env.cache.invalidate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), put_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by ID</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        response = self.opener.get(
            self._get_test_url(get_url_by_id),
            headers={'Content-Type': 'application/json'})

        get_response_json['request']['request_text'] = (
            '<p>This text added to request by ID</p>')

        get_response_json['request']['data'].update({
            "cpu": "4 core",
            "memory": "8 GB",
            "comment": False,
        })

        # Check GET method
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by ID</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        put_data_json = {
            "request_text": "This text added to request by Name",
            "data": {
                "cpu": "8 core",
                "memory": "16 GB",
                "comment": False,
            }
        }

        # PUT request by Request Name
        put_url_by_name = '%s/%s' % (
            self.rest_api_create_vm_endpoint.url, request_new.name)

        response = self.opener.put(
            self._get_test_url(put_url_by_name),
            json=put_data_json)

        self.env.cache.invalidate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), put_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by Name</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)

        response = self.opener.get(
            self._get_test_url(get_url_by_name),
            headers={'Content-Type': 'application/json'})

        get_response_json['request']['request_text'] = (
            '<p>This text added to request by Name</p>')

        get_response_json['request']['data'].update({
            "cpu": "8 core",
            "memory": "16 GB",
            "comment": False,
        })

        # Check GET method
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_response_json)
        self.assertEqual(
            request_new.request_text,
            '<p>This text added to request by Name</p>')
        self.assertEqual(len(request_new.type_id.field_ids), 5)
        self.assertEqual(len(request_new.value_ids), 5)
