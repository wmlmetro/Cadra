Generic Request (Auto routes)
========================================

.. |badge2| image:: https://img.shields.io/badge/license-OPL--1-blue.png
    :target: https://www.odoo.com/documentation/user/12.0/legal/licenses/licenses.html#odoo-apps
    :alt: License: OPL-1

.. |badge3| image:: https://img.shields.io/badge/powered%20by-yodoo.systems-00a09d.png
    :target: https://yodoo.systems
    
.. |badge5| image:: https://img.shields.io/badge/maintainer-CR&D-purple.png
    :target: https://crnd.pro/
    
.. |badge4| image:: https://img.shields.io/badge/docs-Generic_Request_Auto_route-yellowgreen.png
    :target: https://crnd.pro/doc-bureaucrat-itsm/11.0/en/Generic_Request_Auto_route_admin_eng


|badge2| |badge4| |badge5|

Generic Request (Auto route) is a module of the Generic Request application. It helps you to automate request processing. Requests can be moved automatically along the route under certain conditions (by the trigger).

How it works:

- You have set up a request type, configured the request stages and linked them with routes.
- Select the desired route to auto-move the request and add a trigger(s).
- Set up trigger conditions and other attributes if necessary. You can also set up requests to move between stages only in automatic mode.
- When trigger conditions are satisfied, the request will be automatically moved along this route.

Following triggers are implemented:

- Cron: Daily
- Cron: Hourly
- Auto: On Write
- Auto: On Create

Also this module introduces feature *Auto-only* routes.
This feature allows to make routes *auto-only*,
which means that it is not allowed to move requests by this route manualy,
only triggers can move requests by this route.

Read the `Generic Request (Auto route) <https://crnd.pro/doc-bureaucrat-itsm/11.0/en/Generic_Request_Auto_route_admin_eng/>`__ Module Guide for more information.

This module is part of the Bureaucrat ITSM project. 
You can try it by the references below.

Launch your own ITSM system in 60 seconds:
''''''''''''''''''''''''''''''''''''''''''

Create your own `Bureaucrat ITSM <https://yodoo.systems/saas/template/bureaucrat-itsm-demo-data-95>`__ database

|badge3| 

Bug Tracker
===========

Bugs are tracked on `https://crnd.pro/requests <https://crnd.pro/requests>`_.
In case of trouble, please report there.


Maintainer
''''''''''
.. image:: https://crnd.pro/web/image/3699/300x140/crnd.png

Our web site: https://crnd.pro/

This module is maintained by the Center of Research & Development company.

We can provide you further Odoo Support, Odoo implementation, Odoo customization, Odoo 3rd Party development and integration software, consulting services. Our main goal is to provide the best quality product for you. 

For any questions `contact us <mailto:info@crnd.pro>`__.

