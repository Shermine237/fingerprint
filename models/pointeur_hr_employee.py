from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta


class PointeurHrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    # Champs pour l'importation
    import_id = fields.Many2one('pointeur_hr.import', string='Import', readonly=True)
    
    # Champs additionnels pour le pointage
    default_location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage par défaut',
                                        help="Lieu de pointage par défaut de l'employé")
    badge_id = fields.Char(string='ID Badge', help="Identifiant unique du badge de l'employé")
    
    # Statistiques de présence
    attendance_rate = fields.Float(string='Taux de présence', compute='_compute_attendance_stats', store=True)
    total_overtime_hours = fields.Float(string='Total heures supplémentaires', compute='_compute_attendance_stats', store=True)
    total_late_count = fields.Integer(string='Nombre de retards', compute='_compute_attendance_stats', store=True)
    total_early_leave_count = fields.Integer(string='Nombre de départs anticipés', compute='_compute_attendance_stats', store=True)
    
    @api.depends('attendance_ids')
    def _compute_attendance_stats(self):
        for employee in self:
            # Calculer le premier jour du mois en cours
            today = date.today()
            start_date = today.replace(day=1)
            
            # Récupérer les présences valides du mois en cours
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', start_date.strftime('%Y-%m-%d')),
                ('check_in', '<=', today.strftime('%Y-%m-%d 23:59:59')),
                ('check_in', '!=', False)  # Ignorer les lignes sans check_in
            ])

            # Initialiser les compteurs
            total_days = 0
            overtime_hours = 0
            late_count = 0
            early_leave_count = 0

            # Calculer les statistiques
            for attendance in attendances:
                if attendance.attendance_type_ids:
                    types = attendance.attendance_type_ids.split(',')
                    if 'supplementaire' in types:
                        overtime_hours += attendance.working_hours
                    if 'retard' in types:
                        late_count += 1
                    if 'depart_anticipe' in types:
                        early_leave_count += 1
                total_days += 1

            # Calculer le taux de présence (jours de présence / jours ouvrés)
            working_days = self._get_working_days(start_date, today)
            employee.attendance_rate = (total_days / working_days) * 100 if working_days > 0 else 0
            employee.total_overtime_hours = overtime_hours
            employee.total_late_count = late_count
            employee.total_early_leave_count = early_leave_count

    def _get_working_days(self, start_date, end_date):
        """Calculer le nombre de jours ouvrés entre deux dates"""
        # Pour simplifier, on considère 22 jours ouvrés par mois
        return 22

    def action_view_attendances(self):
        """Voir les présences de l'employé"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_attendance.hr_attendance_action")
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'search_default_today': 1}
        return action

    def action_view_overtime(self):
        """Voir les heures supplémentaires de l'employé"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_attendance.hr_attendance_action")
        action['domain'] = [
            ('employee_id', '=', self.id),
            ('attendance_type_ids', 'ilike', 'supplementaire')
        ]
        action['context'] = {'search_default_today': 1}
        return action
