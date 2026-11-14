from .models.project_task_touch import CLOSED_STATES


def fill_touch_date_closed(cr):
    """ The column of the date the tasks were closed, filled for the ones already closed before
    Odoo creates it (it would give them all the date of the install): the date they ended, or
    their last change of stage, or their last change. """
    cr.execute("ALTER TABLE project_task ADD COLUMN IF NOT EXISTS touch_date_closed timestamp")
    cr.execute("""
        UPDATE project_task SET touch_date_closed = COALESCE(date_end, date_last_stage_update, write_date)
         WHERE state IN %s AND touch_date_closed IS NULL
    """, [CLOSED_STATES])


def pre_init_hook(env):
    fill_touch_date_closed(env.cr)
