from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, time


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'
    
    # Champs additionnels pour le pointage
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    attendance_type_ids = fields.Selection([
        ('normal', 'Normal'),
        ('overtime', 'Heures supplémentaires'),
        ('late', 'Retard'),
        ('early_leave', 'Départ anticipé')
    ], string='Types de présence', compute='_compute_working_hours', store=True, multiple=True)
    notes = fields.Text(string='Notes')
    source = fields.Selection([
        ('manual', 'Saisie manuelle'),
        ('import', 'Importé du pointeur')
    ], string='Source', default='manual', required=True, readonly=True)
    
    # Champs calculés
    working_hours = fields.Float(string='Heures travaillées', compute='_compute_working_hours', store=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', compute='_compute_working_hours', store=True)
    regular_hours = fields.Float(string='Heures normales', compute='_compute_working_hours', store=True)
    late_hours = fields.Float(string='Heures de retard', compute='_compute_working_hours', store=True)
    early_leave_hours = fields.Float(string='Heures départ anticipé', compute='_compute_working_hours', store=True)
    
    @api.depends('check_in', 'check_out')
    def _compute_working_hours(self):
        for attendance in self:
            # Initialiser les valeurs
            attendance.working_hours = 0.0
            attendance.regular_hours = 0.0
            attendance.late_hours = 0.0
            attendance.early_leave_hours = 0.0
            attendance.overtime_hours = 0.0
            attendance.attendance_type_ids = []

            if not attendance.check_in or not attendance.check_out:
                continue

            # Calculer la durée totale
            delta = attendance.check_out - attendance.check_in
            total_hours = delta.total_seconds() / 3600.0

            # Obtenir les horaires standards
            calendar = attendance.employee_id.resource_calendar_id
            if not calendar:
                attendance.working_hours = total_hours
                attendance.regular_hours = total_hours
                if total_hours > 0:
                    attendance.attendance_type_ids = ['normal']
                continue

            day_of_week = attendance.check_in.weekday()
            work_hours = self.env['resource.calendar.attendance'].search([
                ('calendar_id', '=', calendar.id),
                ('dayofweek', '=', str(day_of_week))
            ], order='hour_from')

            # Vérifier si c'est un jour férié
            is_holiday = self.env['resource.calendar.leaves'].search([
                ('calendar_id', '=', calendar.id),
                ('date_from', '<=', attendance.check_in),
                ('date_to', '>=', attendance.check_out)
            ], limit=1)

            # Vérifier si c'est un weekend
            is_weekend = day_of_week in (5, 6)  # 5=Samedi, 6=Dimanche

            if is_holiday or is_weekend:
                attendance.working_hours = total_hours
                attendance.overtime_hours = total_hours
                if total_hours > 0:
                    attendance.attendance_type_ids = ['overtime']
                continue

            if not work_hours:
                attendance.working_hours = total_hours
                attendance.regular_hours = total_hours
                if total_hours > 0:
                    attendance.attendance_type_ids = ['normal']
                continue

            # Obtenir les horaires prévus
            start_hour = min(work_hours.mapped('hour_from'))
            end_hour = max(work_hours.mapped('hour_to'))
            
            # Convertir en datetime
            planned_start = attendance.check_in.replace(
                hour=int(start_hour),
                minute=int((start_hour % 1) * 60),
                second=0
            )
            planned_end = attendance.check_in.replace(
                hour=int(end_hour),
                minute=int((end_hour % 1) * 60),
                second=0
            )

            # Calculer les retards et départs anticipés
            if attendance.check_in > planned_start:
                attendance.late_hours = (attendance.check_in - planned_start).total_seconds() / 3600.0
            
            if attendance.check_out < planned_end:
                attendance.early_leave_hours = (planned_end - attendance.check_out).total_seconds() / 3600.0

            # Calculer les heures normales (sans la pause déjeuner)
            attendance.working_hours = total_hours
            if total_hours > 4:  # Déduire la pause déjeuner après 4h
                attendance.working_hours -= 1

            # Les heures normales sont les heures travaillées moins les retards et départs anticipés
            attendance.regular_hours = max(0, attendance.working_hours - attendance.late_hours - attendance.early_leave_hours)

            # Calculer les heures supplémentaires
            standard_hours = sum((line.hour_to - line.hour_from) for line in work_hours)
            if total_hours > 4:  # Déduire la pause déjeuner
                standard_hours -= 1
            
            if attendance.working_hours > standard_hours:
                attendance.overtime_hours = attendance.working_hours - standard_hours

            # Attribuer les types de présence
            types = []
            if attendance.working_hours > 0:
                types.append('normal')
            if attendance.overtime_hours > 0:
                types.append('overtime')
            if attendance.late_hours > 0:
                types.append('late')
            if attendance.early_leave_hours > 0:
                types.append('early_leave')
            attendance.attendance_type_ids = types
    
    def _float_to_time(self, float_hour):
        """Convertit une heure flottante (ex: 7.5) en objet time (07:30:00)"""
        hours = int(float_hour)
        minutes = int((float_hour - hours) * 60)
        return time(hours, minutes)
