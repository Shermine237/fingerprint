from odoo import api, fields, models, tools
from datetime import datetime, timedelta

class HrAttendanceReport(models.Model):
    _name = 'hr.attendance.report'
    _description = 'Rapport de présence'
    _auto = False
    _order = 'date desc, employee_id'

    name = fields.Char(string='Nom', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', readonly=True)
    department_id = fields.Many2one('hr.department', string='Département', readonly=True)
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage', readonly=True)
    default_location_id = fields.Many2one('pointeur_hr.location', string='Lieu par défaut', readonly=True)
    source = fields.Selection([
        ('manual', 'Manuel'),
        ('import', 'Import')
    ], string='Source', readonly=True)
    check_in = fields.Datetime(string='Entrée', readonly=True)
    check_out = fields.Datetime(string='Sortie', readonly=True)
    attendance_type_ids = fields.Char(string='Types de présence', readonly=True)
    working_hours = fields.Float(string='Heures travaillées', readonly=True)
    regular_hours = fields.Float(string='Heures normales', readonly=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', readonly=True)
    late_hours = fields.Float(string='Heures de retard', readonly=True)
    early_leave_hours = fields.Float(string='Heures de départ anticipé', readonly=True)
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Vérifier si la colonne default_location_id existe dans hr_employee
        self.env.cr.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'hr_employee' 
            AND column_name = 'default_location_id'
        """)
        has_default_location = bool(self.env.cr.fetchone())

        # Construire la requête en fonction de l'existence de la colonne
        default_location_field = "e.default_location_id" if has_default_location else "NULL"
        
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH valid_attendances AS (
                    SELECT a.*
                    FROM hr_attendance a
                    WHERE a.check_in IS NOT NULL
                    AND (a.check_out IS NULL OR a.check_in <= a.check_out)
                )
                SELECT
                    a.id as id,
                    CONCAT(e.name, ' - ', to_char(a.check_in, 'YYYY-MM-DD')) as name,
                    a.check_in::date as date,
                    a.employee_id as employee_id,
                    e.department_id as department_id,
                    a.location_id as location_id,
                    %s as default_location_id,
                    a.source as source,
                    a.check_in as check_in,
                    a.check_out as check_out,
                    a.attendance_type_ids as attendance_type_ids,
                    COALESCE(a.working_hours, 0) as working_hours,
                    COALESCE(a.regular_hours, 0) as regular_hours,
                    COALESCE(a.overtime_hours, 0) as overtime_hours,
                    COALESCE(a.late_hours, 0) as late_hours,
                    COALESCE(a.early_leave_hours, 0) as early_leave_hours
                FROM valid_attendances a
                JOIN hr_employee e ON e.id = a.employee_id
            )
        """ % (self._table, default_location_field))
