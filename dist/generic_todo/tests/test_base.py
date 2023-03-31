import logging
from datetime import datetime as d_time
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)

try:
    from freezegun import freeze_time  # noqa
except ImportError:  # pragma: no cover
    _logger.warning("freezegun not installed. Tests will not work!")


class TestTodoBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestTodoBase, cls).setUpClass()

        cls.Todo = cls.env['generic.todo']
        cls.todo_simple = cls.env.ref('generic_todo.generic_todo_type_simple')

    def test_start_complete_todo(self):

        # Create todo
        with freeze_time('2022-08-06 12:07:00'):
            todo_1 = self.Todo.create({
                'name': 'Test Todo 1',
                'todo_type_id': self.todo_simple.id,
            })

        self.assertEqual(todo_1.name, 'Test Todo 1')
        self.assertEqual(todo_1.state, 'new')
        # Sequence is equal to 5, default value because todo no have related
        # document
        self.assertEqual(todo_1.sequence, 5)
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertFalse(todo_1.date_started)
        self.assertFalse(todo_1.date_completed)
        self.assertFalse(todo_1.date_last_action)

        # Start todo_1
        with freeze_time('2022-08-06 13:01:00'):
            todo_1.action_start_work()

        self.assertEqual(todo_1.state, 'in_progress')
        # Sequence is equal to 5, default value because todo no have related
        # document
        self.assertEqual(todo_1.sequence, 5)
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 1))

        # Complete todo_1
        with freeze_time('2022-08-06 14:11:00'):
            todo_1.action_complete_work()

        self.assertEqual(todo_1.state, 'done')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertEqual(todo_1.date_completed, d_time(2022, 8, 6, 14, 11))
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 14, 11))

    def test_start_pause_start_complete_todo(self):

        # Create todo
        with freeze_time('2022-08-06 12:07:00'):
            todo_1 = self.Todo.create({
                'name': 'Test Todo 1',
                'todo_type_id': self.todo_simple.id,
            })

        self.assertEqual(todo_1.name, 'Test Todo 1')
        self.assertEqual(todo_1.state, 'new')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertFalse(todo_1.date_started)
        self.assertFalse(todo_1.date_completed)
        self.assertFalse(todo_1.date_last_action)

        # Start todo_1
        with freeze_time('2022-08-06 13:01:00'):
            todo_1.action_start_work()

        self.assertEqual(todo_1.state, 'in_progress')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 1))

        # Pause todo_1
        with freeze_time('2022-08-06 13:21:00'):
            todo_1.action_pause_work()

        self.assertEqual(todo_1.state, 'paused')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 21))

        # Unpause todo_1
        with freeze_time('2022-08-06 13:29:00'):
            todo_1.action_start_work()

        self.assertEqual(todo_1.state, 'in_progress')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 29))

        # Complete todo_1
        with freeze_time('2022-08-06 14:11:00'):
            todo_1.action_complete_work()

        self.assertEqual(todo_1.state, 'done')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertEqual(todo_1.date_completed, d_time(2022, 8, 6, 14, 11))
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 14, 11))

    def test_start_pause_start_cancel_todo(self):

        # Create todo
        with freeze_time('2022-08-06 12:07:00'):
            todo_1 = self.Todo.create({
                'name': 'Test Todo 1',
                'todo_type_id': self.todo_simple.id,
            })

        self.assertEqual(todo_1.name, 'Test Todo 1')
        self.assertEqual(todo_1.state, 'new')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertFalse(todo_1.date_started)
        self.assertFalse(todo_1.date_completed)
        self.assertFalse(todo_1.date_last_action)

        # Start todo_1
        with freeze_time('2022-08-06 13:01:00'):
            todo_1.action_start_work()

        self.assertEqual(todo_1.state, 'in_progress')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 1))

        # Pause todo_1
        with freeze_time('2022-08-06 13:21:00'):
            todo_1.action_pause_work()

        self.assertEqual(todo_1.state, 'paused')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 21))

        # Unpause todo_1
        with freeze_time('2022-08-06 13:29:00'):
            todo_1.action_start_work()

        self.assertEqual(todo_1.state, 'in_progress')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 13, 29))

        # Complete todo_1
        with freeze_time('2022-08-06 14:11:00'):
            todo_1.action_cancel_work()

        self.assertEqual(todo_1.state, 'canceled')
        self.assertEqual(todo_1.date_created, d_time(2022, 8, 6, 12, 7))
        self.assertEqual(todo_1.date_started, d_time(2022, 8, 6, 13, 1))
        self.assertFalse(todo_1.date_completed)
        self.assertEqual(todo_1.date_last_action, d_time(2022, 8, 6, 14, 11))
