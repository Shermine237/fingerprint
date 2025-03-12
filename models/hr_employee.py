from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta


class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    # Champs additionnels pour le pointage
    default_location_id = fields.Many2one('pointeur.location', string='Lieu de pointage par défaut')
    badge_id = fields.Char(string='ID Badge', help="Identifiant unique du badge de l'employé")
    
    # Statistiques de présence
    total_overtime_hours = fields.Float(string='Total heures supplémentaires', compute='_compute_attendance_stats')
    total_late_count = fields.Integer(string='Nombre de retards', compute='_compute_attendance_stats')
    total_early_leave_count = fields.Integer(string='Nombre de départs anticipés', compute='_compute_attendance_stats')
    attendance_rate = fields.Float(string='Taux de présence (%)', compute='_compute_attendance_stats')
    
    @api.depends()
    def _compute_attendance_stats(self):
        # Période de calcul (mois en cours par défaut)
        today = fields.Date.today()
        first_day = today.replace(day=1)
        last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        for employee in self:
            # Récupérer toutes les présences du mois en cours
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', first_day),
                ('check_in', '<=', last_day),
                ('check_out', '!=', False)
            ])
            
            # Calculer les statistiques
            employee.total_overtime_hours = sum(attendances.mapped('overtime_hours'))
            employee.total_late_count = len(attendances.filtered(lambda a: a.attendance_type == 'late'))
            employee.total_early_leave_count = len(attendances.filtered(lambda a: a.attendance_type == 'early_leave'))
            
            # Calculer le taux de présence
            # Nombre de jours ouvrés dans le mois
            calendar = employee.resource_calendar_id
            if not calendar:
                employee.attendance_rate = 0.0
                continue
                
            # Calculer le nombre de jours de travail attendus dans la période
            work_days = 0
            current_date = first_day
            while current_date <= last_day:
                day_of_week = current_date.weekday()
                has_work = self.env['resource.calendar.attendance'].search_count([
                    ('calendar_id', '=', calendar.id),
                    ('dayofweek', '=', str(day_of_week))
                ]) > 0
                
                if has_work:
                    # Vérifier si ce n'est pas un jour férié
                    is_holiday = self.env['resource.calendar.leaves'].search_count([
                        ('calendar_id', '=', calendar.id),
                        ('date_from', '<=', current_date),
                        ('date_to', '>=', current_date),
                        ('resource_id', '=', False)  # Congés globaux
                    ]) > 0
                    
                    if not is_holiday:
                        work_days += 1
                
                current_date += timedelta(days=1)
            
            # Nombre de jours avec au moins une présence
            attendance_days = len(set(att.check_in.date() for att in attendances))
            
            # Calculer le taux de présence
            if work_days > 0:
                employee.attendance_rate = (attendance_days / work_days) * 100
            else:
                employee.attendance_rate = 0.0
    
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
            ('attendance_type', '=', 'overtime')
        ]
        action['context'] = {'default_employee_id': self.id}
        action['name'] = _('Heures supplémentaires de %s') % self.name
        return action
