import logging

from werkzeug import urls

from .test_api_endpoint_base import TestApiEndpointsBase
from ..constants import KEY_CRYPT_CONTEXT

_logger = logging.getLogger(__name__)

hash_api_key = (
    getattr(KEY_CRYPT_CONTEXT, 'hash', None) or KEY_CRYPT_CONTEXT.encrypt
)

verify_api_key = getattr(KEY_CRYPT_CONTEXT, 'verify', None)
if not verify_api_key:
    _logger.debug('No loaded verification method')


class TestRequestApiEndpointREST(TestApiEndpointsBase):

    def test_rest_api_endpoint_request_author(self):
        # pylint: disable=too-many-statements
        self.assertFalse(len(self.rest_api_endpoint.api_key_ids))
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
        self.assertFalse(request_new.author_id)
        self.assertFalse(request_new.author_name)
        self.assertFalse(request_new.author_phone)
        self.assertEqual(request_new.email_from, email_without_partner)

        # Email (with name) without related partner
        email_author_name = 'Test Email Name Author'
        post_data_json = {
            "author": {
                "email": email_without_partner,
                "name": email_author_name
            },
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        # Update data by new request name
        post_response_json['request']['name'] = request_new.name

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>Test Rest API endpoint</p>')
        self.assertFalse(request_new.author_id)
        self.assertEqual(request_new.author_name, email_author_name)
        self.assertFalse(request_new.author_phone)
        self.assertEqual(request_new.email_from, email_without_partner)

        # Phone without related partner
        phone_without_partner = '+9 999-999-9999'
        post_data_json = {
            "author": {
                "email": email_without_partner,
                "phone": phone_without_partner
            },
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        # Update data by new request name
        post_response_json['request']['name'] = request_new.name

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>Test Rest API endpoint</p>')
        self.assertFalse(request_new.author_id)
        self.assertFalse(request_new.author_name)
        self.assertEqual(request_new.author_phone, phone_without_partner)
        self.assertEqual(request_new.email_from, email_without_partner)

        # Phone (with name) without related partner
        phone_author_name = 'Test Phone Name Author'
        post_data_json = {
            "author": {
                "email": email_without_partner,
                "phone": phone_without_partner,
                "name": phone_author_name,
            },
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        # Update data by new request name
        post_response_json['request']['name'] = request_new.name

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>Test Rest API endpoint</p>')
        self.assertFalse(request_new.author_id)
        self.assertEqual(request_new.author_name, phone_author_name)
        self.assertEqual(request_new.author_phone, phone_without_partner)
        self.assertEqual(request_new.email_from, email_without_partner)

        # Email with related partner
        partner_demo = self.env.ref('base.partner_demo')
        post_data_json = {
            "author": {
                "email": partner_demo.email
            },
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        # Update data by new request name
        post_response_json['request']['name'] = request_new.name

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>Test Rest API endpoint</p>')
        self.assertEqual(request_new.author_id, partner_demo)
        self.assertEqual(request_new.author_name, partner_demo.name)
        self.assertEqual(request_new.author_phone, partner_demo.phone)
        self.assertEqual(request_new.email_from, partner_demo.email)

        # Phone with related partner
        # TODO: What should we do if the phone number sent does not
        # match the phone number of the partner?
        post_data_json = {
            "author": {
                "email": partner_demo.email,
                "phone": partner_demo.email
            },
        }

        requests_before = self.Request.search([])

        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        # Update data by new request name
        post_response_json['request']['name'] = request_new.name

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), post_response_json)
        self.assertEqual(len(request_new), 1)
        self.assertEqual(
            request_new.request_text, '<p>Test Rest API endpoint</p>')
        self.assertEqual(request_new.author_id, partner_demo)
        self.assertEqual(request_new.author_name, partner_demo.name)
        self.assertEqual(request_new.author_phone, partner_demo.phone)
        self.assertEqual(request_new.email_from, partner_demo.email)

    def test_rest_api_endpoint_request_text(self):
        self.assertFalse(len(self.rest_api_endpoint.api_key_ids))
        post_data_json = {
            "author": {
                "email": "author's email",
                "name": "author's first name (optional)",
                "phone": "author's phone (optional)",
            },
            "request_text": "Text of request created by REST API.",
        }

        requests_before = self.Request.search([])

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
            request_new.request_text,
            '<p>Text of request created by REST API.</p>')

    def test_rest_api_endpoint_controllers(self):
        self.assertFalse(len(self.rest_api_endpoint.api_key_ids))
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
            json=post_data_json,
        )

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

    def test_rest_api_endpoint_authorization_api_key(self):
        # pylint: disable=too-many-statements
        # pylint: disable=too-many-locals
        # Authentication with Keys
        self.assertFalse(len(self.rest_api_endpoint_with_auth.api_key_ids))

        # Add New Api Key by wizard
        name_of_key = 'Key from wizard'
        action = self.rest_api_endpoint_with_auth.action_add_access_key()
        wizard = self.env[action['res_model']].with_context(
            **action['context']).create({
                'name': name_of_key,
            })

        self.assertEqual(
            wizard.api_endpoint_id, self.rest_api_endpoint_with_auth)

        self.assertEqual(wizard.name, name_of_key)

        keys_before = self.env['request.api.key'].search([])

        action_show_key = wizard.do_generate_and_add_access_key()
        created_key_value = action_show_key['context']['default_key']

        wizard_key_show = self.env[action_show_key['res_model']].with_context(
            **action_show_key['context']).create({})

        # TODO: Maybe need add some another check EndpointAPIKeyShow wizard
        # but when on field 'key' set parameter store=False
        # wizard_key_show.key return False in tests, on webinterface all work.
        self.assertEqual(
            wizard_key_show.env.context['default_key'], created_key_value)

        # NEW Key created from wizard
        new_key_from_wizard = self.env['request.api.key'].search([
            ('id', 'not in', keys_before.ids)])

        # Check the wizard, it must be deleted
        self.assertFalse(wizard.exists())

        self.assertEqual(len(self.rest_api_endpoint_with_auth.api_key_ids), 1)

        self.assertEqual(new_key_from_wizard.name, name_of_key)
        self.assertEqual(
            new_key_from_wizard.api_endpoint_id,
            self.rest_api_endpoint_with_auth)
        self.assertTrue(
            verify_api_key(created_key_value, new_key_from_wizard.key_value))
        self.assertFalse(new_key_from_wizard.use_sudo)
        self.assertFalse(new_key_from_wizard.sudo_user_id)

        email_without_partner = "not_an_exising@email"
        post_data_json = {
            "author": {
                "email": email_without_partner
            },
        }

        requests_before = self.Request.search([])

        # Access is not available because no authentication data
        # was provided
        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint_with_auth.url),
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        # Access is not available because the wrong header and authentication
        # key where passed
        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint_with_auth.url),
            headers={'wrong-header': 'wrong_key'},
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        # Access is not available because the wrong header and right
        # authentication key where passed
        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint_with_auth.url),
            headers={'wrong-header': created_key_value},
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        # Access is not available because the correct header and
        # incorrect authentication key where passed
        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint_with_auth.url),
            headers={'X-API-Key': 'wrong_key'},
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        requests_before = self.Request.search([])

        # There is access because the correct header and
        # authentication key where passed
        response = self.opener.post(
            self._get_test_url(self.rest_api_endpoint_with_auth.url),
            headers={'X-API-Key': created_key_value},
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
        self.assertFalse(request_new.author_id)
        self.assertFalse(request_new.author_name)
        self.assertFalse(request_new.author_phone)
        self.assertEqual(request_new.email_from, email_without_partner)

        # Use Query Parameters
        requests_before = self.Request.search([])
        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        # Access is not available because the wrong query parameter and
        # authentication key where passed

        url = urls.url_parse(
            self._get_test_url(self.rest_api_endpoint_with_auth.url)
        )
        # Prepare url
        query_params = {'wrong_parameter': 'wrong_key'}
        url_with_params = url.replace(
            query=urls.url_encode(query_params)).to_url()

        response = self.opener.post(
            url_with_params,
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        # Access is not available because the incorrect query parameter and
        # correct authentication key where passed

        # Prepare url
        query_params = {'wrong_parameter': created_key_value}
        url_with_params = url.replace(
            query=urls.url_encode(query_params)).to_url()

        response = self.opener.post(
            url_with_params,
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        # Access is not available because the correct query parameter and
        # incorrect password where passed

        # Prepare url
        query_params = {'api_key': 'wrong_key'}
        url_with_params = url.replace(
            query=urls.url_encode(query_params)).to_url()

        response = self.opener.post(
            url_with_params,
            json=post_data_json)

        request_new = self.Request.search([
            ('id', 'not in', requests_before.ids)])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')
        self.assertFalse(len(request_new))

        requests_before = self.Request.search([])

        # There is access because the correct query parameter and
        # authentication key where passed

        # Prepare url
        query_params = {'api_key': created_key_value}
        url_with_params = url.replace(
            query=urls.url_encode(query_params)).to_url()

        response = self.opener.post(
            url_with_params,
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
        self.assertFalse(request_new.author_id)
        self.assertFalse(request_new.author_name)
        self.assertFalse(request_new.author_phone)
        self.assertEqual(request_new.email_from, email_without_partner)
