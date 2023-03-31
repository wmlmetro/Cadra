Generic System Event
====================

.. |badge1| image:: https://img.shields.io/badge/pipeline-pass-brightgreen.png
    :target: https://github.com/crnd-inc/generic-addons

.. |badge2| image:: https://img.shields.io/badge/license-LGPL--3-blue.png
    :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3

.. |badge3| image:: https://img.shields.io/badge/powered%20by-yodoo.systems-00a09d.png
    :target: https://yodoo.systems

.. |badge5| image:: https://img.shields.io/badge/maintainer-CR&D-purple.png
    :target: https://crnd.pro/


|badge1| |badge2| |badge5|

This module provides framework that allows to make odoo event-driven.
Note, that in this case *event* means *business event*.

With this module, you can easily convert your model to event source,
and then handle events from that model in any other place of odoo.
With this module you may forget about again and again overriding ``write`` methods.


Why this is needed?
'''''''''''''''''''

This module allows to step away from infinite overrides of write/create,
or overriding other methods to add some logic. Instead, with this framework,
you can think in event driven way: just trigger event with all needed data
where it is needed. And handle this event in multiple places in multiple modules,
in multiple related models.

For example, you can define event like *Invoice Paid*, and then handle it
on Sale Order, In CRM, or in any other related object. The framework, will
automatically call all registered handlers of this event.
This way, it is possible to significantly simplify complex logic of handling
events.

Also, because events are stored in database, you always have history
of events related to specific record, which could help in debug,
or in tracking what is going on in some cases.


How to use
''''''''''


1. Create model for events
~~~~~~~~~~~~~~~~~~~~~~~~~~

At first, you have to create model to store events produced by your event source.
You can define such model as following:

.. code:: python

    class MyEvent(models.Model):
        _name = 'my.event'
        _inherit = 'generic.system.event.data.mixin'

        # You can add here fields specific to your events.
        # For example:
        my_param_old = fields.Char()
        my_param_new = fields.Char()


2. Create event source
~~~~~~~~~~~~~~~~~~~~~~

You have to inherit your model from ``generic.system.event.source.mixin`` to
to make it event source, capable to generate events.
For example, let's define simple model with one field ``param``,
and trigger event any type this field changed.

.. code:: python

    from odoo.addons.generic_mixin import post_write
    from odoo.addons.generic_system_event import on_event


    class MyEventSource(models.Model):
         _name = 'my.event.source'
         _inherit = 'generic.system.event.source.mixin'

         # This is needed to automatically register event source
         # Other wise, you will need additionally to define
         # event source in XML.
         # Automatic event source will be generated with
         # xmlid: your_module_name.system_event_source__my_event_source
         _generic_system_event_source__auto_create = True

         # name of data model for events from this event source
         _generic_system_event_source__event_data_model = 'my.event'

         # Next, we can define some data on this model
         my_param = fields.Char()

         # This field will be changed automatically by event handler.
         counter = Integer

         # Let's trigger event
         @post_write('my_param')
         def _after_my_param_changed_trigger_event(self, changes):
             # The line below triggers event
             self.trigger_event('my-param-changed', {
                 'my_param_old': changes['my_param'].old_val,
                 'my_param_new': changes['my_param'].new_val,
             })

         # Next, we can define event handler:
         @on_event('my-param-changed')
         def _on_my_param_changed(self, event):
             self.counter += 1

3. Define event types
~~~~~~~~~~~~~~~~~~~~~

Next, we have to define all event types in the XML.

.. code:: xml

    <!-- define category for events related to this model -->
    <record model="generic.system.event.category"
            id="system_event_category_my_events">
        <field name="name">My Events</field>
        <field name="code">my-events</field>
        <field name="event_source_id"
               ref="my_module.system_event_source__my_event_source"/>
    </record>

    <!-- Define event type for our events -->
    <record model="generic.system.event.type" id="system_event_type_my_param_changed">
        <field name="name">My Param Changed</field>
        <field name="code">my-param-changed</field>
        <field name="event_category_id" ref="system_event_category_my_events"/>
        <field name="event_source_id"
               ref="my_module.system_event_source__my_event_source"/>
    </record>

4. Define views for events
~~~~~~~~~~~~~~~~~~~~~~~~~~

Next we have to define views for event data model
(that model that is used to store events).

.. code:: xml

    <record id="view_my_event_tree" model="ir.ui.view">
        <field name="model">my.event</field>
        <field name="inherit_id" ref="generic_system_event.view_generic_generic_system_event_tree"/>
        <field name="mode">primary</field>
        <field name="arch" type="xml">
            <xpath expr="/tree" position="attributes">
                <attribute name="create">false</attribute>
                <attribute name="edit">false</attribute>
            </xpath>
        </field>
    </record>

    <record id="view_my_event_form" model="ir.ui.view">
        <field name="model">my.event</field>
        <field name="inherit_id" ref="generic_system_event.view_generic_system_event_form"/>
        <field name="mode">primary</field>
        <field name="arch" type="xml">
            <xpath expr="//group[@name='group_event']/field[@name='event_type_id']"
                   position="before">
                <field name="event_id"/>
            </xpath>
            <xpath expr="//group[@name='group_data_root']"
                   position="inside">
                <group string="My Param Changed"
                       name="group_my_param_changed"
                       attrs="{'invisible': [('event_code', '!=', 'my-param-changed')]}">
                    <field name="my_param_old"/>
                    <field name="my_param_new"/>
                </group>
            </xpath>
        </field>
    </record>

5. Add stat-button to show events on your view
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If needed, you can add stat-button on your form view of 'my.event.source'
to show related events. All you need is to add following xml snippet.

.. code:: xml


    <div class="oe_button_box" name="button_box">
        <button class="oe_stat_button" type="object"
                groups="base.group_no_one"
                name="action_show_related_system_events"
                icon="fa-cogs">
            <field name="generic_event_count"
                   widget="statinfo"
                   string="Events"/>
        </button>
    </div>

Note, that method ``action_show_related_system_events`` already implemented
in ``generic.system.event.source.mixin``, thus, this xml-snipped is all you need.


Advanced usage
''''''''''''''

For advanced usage, look for documentation in the code.
Basically, this framework, allows you to handle events triggered
in context of one model (for example invoices),
in context of another related model (for example sale order).
All you need for this, is to specify mapping in XML
(see ``generic.system.event.source.handler.map`` model for more info).
Also, in this case, you have to apply ``generic.system.event.handler.mixin``
to handler model to allow framework to automatically discover handlers.


Launch your own ITSM system in 60 seconds:
''''''''''''''''''''''''''''''''''''''''''

Create your own `Bureaucrat ITSM <https://yodoo.systems/saas/template/bureaucrat-itsm-demo-data-95>`__ database

|badge3|


Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/crnd-inc/generic-addons/issues>`_.
In case of trouble, please check there if your issue has already been reported.


Maintainer
''''''''''
.. image:: https://crnd.pro/web/image/3699/300x140/crnd.png

Our web site: https://crnd.pro/

This module is maintained by the Center of Research & Development company.

We can provide you further Odoo Support, Odoo implementation, Odoo customization, Odoo 3rd Party development and integration software, consulting services. Our main goal is to provide the best quality product for you.

For any questions `contact us <mailto:info@crnd.pro>`__.
