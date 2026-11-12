""" Files (Expedientes, project_task_touch) of the demo: templates of the management of the yard
and projects created from them, at different moments, with their tasks, subtasks, dependencies
and deadlines relative to the day of the installation. """
from dateutil.relativedelta import relativedelta

from odoo import Command, fields

MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
          'octubre', 'noviembre', 'diciembre']
# Subtasks of each course of the training
COURSE_STEPS = ['Inscripción', 'Asistencia', 'Certificado entregado']

# Templates: (key, name, tag, description, tasks). A task: (key, name, keys of the tasks it
# depends on, days from the start of the project to its deadline, subtasks)
TEMPLATES = [
    ('waste', 'Salida de residuos', 'Medio ambiente',
     "Una única tarea, que se repite cada mes: la retirada de los residuos peligrosos por un gestor autorizado.",
     [('pickup', 'Retirada de residuos con gestor autorizado', [], 24,
       ['Preparar el documento de identificación (DI)', 'Pesar y etiquetar los contenedores',
        'Firmar el DI con el gestor', 'Anotar la salida en el archivo cronológico'])]),
    ('onboarding', 'Onboarding de empleado', 'Laboral',
     "Incorporación de una persona: del contrato a su primera semana.",
     [('contract', 'Contrato y alta en la Seguridad Social', [], 0, []),
      ('record', 'Ficha de empleado y datos de nómina', ['contract'], 2, []),
      ('medical', 'Reconocimiento médico', ['contract'], 7, []),
      ('ppe', 'Entrega de EPIs y ropa de trabajo', ['contract'], 1, []),
      ('prl', 'Formación inicial en prevención de riesgos', ['ppe'], 5, []),
      ('access', 'Usuario de Odoo y accesos', ['record'], 3, []),
      ('welcome', 'Presentación al equipo y acompañamiento la primera semana', ['prl', 'access'], 10, [])]),
    ('aeat', 'Gestión AEAT mensual', 'Fiscal',
     "Las obligaciones de un mes con Hacienda, a presentar hasta el día 20 del mes siguiente.",
     [('invoices', 'Revisar facturas emitidas y recibidas', [], 5, []),
      ('banks', 'Conciliar bancos', [], 7, []),
      ('m303', 'Modelo 303 (IVA)', ['invoices', 'banks'], 15, []),
      ('m111', 'Modelo 111 (retenciones de IRPF)', ['invoices'], 15, []),
      ('m115', 'Modelo 115 (retenciones de alquileres)', ['invoices'], 15, []),
      ('submit', 'Presentar en la sede electrónica de la AEAT', ['m303', 'm111', 'm115'], 19, []),
      ('archive', 'Archivar los justificantes de presentación', ['submit'], 22, [])]),
    ('training', 'Formación de taller', 'Formación',
     "Los cursos de una persona del taller: primero la prevención de riesgos, después los específicos.",
     [('prl', 'Curso PRL específico de taller (20 h)', [], 7, COURSE_STEPS),
      ('vfu', 'Descontaminación de vehículos al final de su vida útil', ['prl'], 21, COURSE_STEPS),
      ('forklift', 'Carretilla elevadora (operador)', ['prl'], 30, COURSE_STEPS),
      ('ev', 'Seguridad en vehículos híbridos y eléctricos', ['prl'], 45, COURSE_STEPS),
      ('cutting', 'Herramientas de corte y oxicorte', ['prl'], 45, COURSE_STEPS),
      ('review', 'Evaluación final con el jefe de taller', ['vfu', 'forklift', 'ev', 'cutting'], 60, [])]),
]

# For each template, the names of its tasks by key
TASK_NAMES = {key: {task_key: name for task_key, name, *_r in tasks} for key, _n, _t, _d, tasks in TEMPLATES}


def create_files(env):
    """ The templates and the files of the demo. """
    today = fields.Date.context_today(env.user)
    templates = {key: _create_template(env, key, *values) for key, *values in TEMPLATES}

    # Waste: one task, repeated each month; the one of the last month done, so that Odoo created
    # the one of this month
    last_month = today + relativedelta(months=-1, day=1)
    waste = _create_file(env, templates, 'waste', 'Salida de residuos', last_month)
    pickup = waste.task_ids.filtered(lambda task: not task.parent_id)
    pickup.child_ids.state = '1_done'
    pickup.state = '1_done'

    # Onboarding: one person in their second week, another starting today
    onboarding = _create_file(env, templates, 'onboarding', 'Onboarding Juan Pérez (mecánico)', today - relativedelta(days=8))
    _close(onboarding, 'onboarding', ['contract', 'record', 'ppe', 'access', 'medical'])
    _create_file(env, templates, 'onboarding', 'Onboarding Laura Martín (administración)', today)

    # AEAT: the month before the last one presented, the last one in progress (until the 20th)
    for months, done in ((-2, True), (-1, False)):
        month = today + relativedelta(months=months, day=1)
        file = _create_file(env, templates, 'aeat', f'AEAT {MONTHS[month.month - 1]} {month.year}', month + relativedelta(months=1))
        _close(file, 'aeat', None if done else ['invoices', 'banks', 'm111'])

    # Training: the course of risks done, the specific ones under way
    training = _create_file(env, templates, 'training', 'Formación de taller · Juan Pérez', today - relativedelta(days=25))
    _close(training, 'training', ['prl'])
    vfu = _task(training, 'training', 'vfu')
    vfu.child_ids.filtered(lambda subtask: subtask.name in COURSE_STEPS[:2]).state = '1_done'
    _task(training, 'training', 'forklift').child_ids.filtered(lambda subtask: subtask.name == COURSE_STEPS[0]).state = '1_done'
    return templates


def _create_template(env, key, name, tag, description, tasks):
    """ A template with planned dates, from the 1st of January, and deadlines in its tasks: the
    files made of it get them moved to their start (see project_task_touch). """
    stages = env.ref('scrap_demo.task_stage_todo') | env.ref('scrap_demo.task_stage_doing') | env.ref('scrap_demo.task_stage_done')
    start = fields.Date.context_today(env.user) + relativedelta(month=1, day=1)
    deadline = env['project.task.touch']._to_deadline
    template = env['project.project'].create({
        'name': name,
        'date_start': start,
        'date': start + relativedelta(days=max(days for _k, _n, _d, days, _s in tasks)),
        'description': f'<p>{description}</p>',
        'touch_ok': True,
        'type_ids': [Command.set(stages.ids)],
        'allow_task_dependencies': any(depends for _k, _n, depends, *_r in tasks),
        'allow_recurring_tasks': key == 'waste',
        'tag_ids': [Command.set(_tag(env, tag).ids)],
    })
    template._toggle_template_mode(True)
    Task = env['project.task']
    by_key = {}
    for sequence, (task_key, task_name, depends, days, subtasks) in enumerate(tasks):
        task = Task.create({
            'name': task_name,
            'project_id': template.id,
            'sequence': sequence,
            'tag_ids': [Command.set(_tag(env, tag).ids)],
            'depend_on_ids': [Command.set([by_key[depend].id for depend in depends])],
            'date_deadline': deadline(start + relativedelta(days=days)),
            **({'recurring_task': True, 'repeat_interval': 1, 'repeat_unit': 'month', 'repeat_type': 'forever'}
               if key == 'waste' else {}),
        })
        Task.create([{
            'name': subtask,
            'project_id': template.id,
            'parent_id': task.id,
            'sequence': step,
        } for step, subtask in enumerate(subtasks)])
        by_key[task_key] = task
    return template


def _create_file(env, templates, key, name, date_start):
    """ A file from the template, as with "New file" of the screen, assigned to the admin: its end
    and the deadlines of its tasks come from the template, moved to its start. """
    file = templates[key].action_create_from_template({'name': name, 'date_start': date_start})
    file.touch_ok = True
    file.task_ids.user_ids = env.ref('base.user_admin')
    return file


def _task(file, template_key, key):
    return file.task_ids.filtered(lambda task: task.name == TASK_NAMES[template_key][key] and not task.parent_id)


def _close(file, template_key, keys):
    """ The tasks of the keys done (all of them if None), with their subtasks, in their order, so
    that the ones depending on them are no longer waiting. """
    tasks = file.task_ids.filtered(lambda task: not task.parent_id).sorted('sequence')
    if keys is not None:
        names = {TASK_NAMES[template_key][key] for key in keys}
        tasks = tasks.filtered(lambda task: task.name in names)
    for task in tasks:
        task.child_ids.state = '1_done'
        task.state = '1_done'


def _tag(env, name):
    return env['project.tags'].search([('name', '=', name)], limit=1) or env['project.tags'].create({'name': name})
