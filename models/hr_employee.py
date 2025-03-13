from . import pointeur_location  # Doit être chargé en premier
from . import hr_employee
from . import hr_attendance
from . import hr_attendance_report
from . import pointeur_import
from . import pointeur_import_line
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta


class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    # Champs pour l'importation
    import_id = fields.Many2one('pointeur_hr.import', string='Import', readonly=True)
    
    # Champs additionnels pour le pointage
    default_location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage par défaut')
    badge_id = fields.Char(string='ID Badge', help="Identifiant unique du badge de l'employé")
    
    # Statistiques de présence
    total_overtime = fields.Float(string='Total heures supplémentaires', compute='_compute_attendance_stats', store=True)
    total_late = fields.Float(string='Total retards', compute='_compute_attendance_stats', store=True)
    total_early_leave = fields.Float(string='Total départs anticipés', compute='_compute_attendance_stats', store=True)
    
    @api.depends('attendance_ids.overtime_hours', 'attendance_ids.late_hours', 'attendance_ids.early_leave_hours')
    def _compute_attendance_stats(self):
        for employee in self:
            # Récupérer uniquement les présences valides (avec heure d'entrée)
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '!=', False)
            ])
            employee.total_overtime = sum(attendances.mapped('overtime_hours'))
            employee.total_late = sum(attendances.mapped('late_hours'))
            employee.total_early_leave = sum(attendances.mapped('early_leave_hours'))
    
    def action_view_attendances(self):
        """Ouvre une vue des présences de l'employé"""
        self.ensure_one()
        action = self.env.ref('hr_attendance.hr_attendance_action').read()[0]
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action
    
    def action_view_overtime(self):
        """Ouvre une vue des heures supplémentaires de l'employé"""
        self.ensure_one()
        action = self.env.ref('hr_attendance.hr_attendance_action').read()[0]
        action['domain'] = [
            ('employee_id', '=', self.id),
            ('attendance_type_ids.code', '=', 'overtime')
        ]
        action['context'] = {'default_employee_id': self.id}
        action['name'] = _('Heures supplémentaires de %s') % self.name
        return action
