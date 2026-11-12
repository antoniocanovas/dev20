""" The deadline time of the tasks (datetime_deadline, from v17) to the deadline of Odoo, which is
a datetime since v18: the kanban, the list and their colours use it. The old field shown in its
place in the form was never copied to it. Its column is dropped by Odoo at the end of the update,
as the one of any field removed. """
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'project_task' AND column_name = 'datetime_deadline'
    """)
    if not cr.fetchone():
        return
    # The ones without a deadline of Odoo: the deadline written in the form
    cr.execute("""
        UPDATE project_task
           SET date_deadline = datetime_deadline
         WHERE datetime_deadline IS NOT NULL AND date_deadline IS NULL
    """)
    _logger.info("Deadline of %s tasks taken from datetime_deadline", cr.rowcount)
