from odoo import api, fields, models, tools
from datetime import datetime, timedelta

class HrAttendanceReport(models.Model):
    _name = 'hr.attendance.report'
    _description = 'Rapport détaillé des présences'
    _auto = False
    _order = 'date desc'

    name = fields.Char(string='Nom', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', readonly=True)
    department_id = fields.Many2one('hr.department', string='Département', readonly=True)
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage', readonly=True)
    source = fields.Selection([
        ('manual', 'Saisie manuelle'),
        ('import', 'Importé du pointeur')
    ], string='Source', readonly=True)
    check_in = fields.Datetime(string='Entrée', readonly=True)
    check_out = fields.Datetime(string='Sortie', readonly=True)
    working_hours = fields.Float(string='Heures travaillées', readonly=True)
    regular_hours = fields.Float(string='Heures normales', readonly=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', readonly=True)
    late_hours = fields.Float(string='Heures de retard', readonly=True)
    early_leave_hours = fields.Float(string='Heures départ anticipé', readonly=True)
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    a.id as id,
                    CONCAT(e.name, ' - ', to_char(a.check_in, 'YYYY-MM-DD')) as name,
                    DATE(a.check_in) as date,
                    a.employee_id as employee_id,
                    e.department_id as department_id,
                    a.location_id as location_id,
                    a.source as source,
                    a.check_in as check_in,
                    a.check_out as check_out,
                    a.working_hours as working_hours,
                    a.regular_hours as regular_hours,
                    a.overtime_hours as overtime_hours,
                    a.late_hours as late_hours,
                    a.early_leave_hours as early_leave_hours
                FROM hr_attendance a
                JOIN hr_employee e ON a.employee_id = e.id
                WHERE a.check_out IS NOT NULL
            )
        """ % self._table)
