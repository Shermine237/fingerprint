from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, time


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'
    
    # Champs additionnels pour le pointage
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    attendance_type_ids = fields.Many2many(
        'pointeur_hr.attendance.type',
        string='Types de présence',
        compute='_compute_attendance_types',
        store=True
    )
    notes = fields.Text(string='Notes')
    source = fields.Selection([
        ('manual', 'Saisie manuelle'),
        ('import', 'Importé du pointeur')
    ], string='Source', default='manual', required=True, readonly=True)
    
    # Champs calculés
    working_hours = fields.Float(string='Heures travaillées', compute='_compute_working_hours', store=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', compute='_compute_overtime_hours', store=True)
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
                continue

            day_of_week = attendance.check_in.weekday()
            work_hours = self.env['resource.calendar.attendance'].search([
                ('calendar_id', '=', calendar.id),
                ('dayofweek', '=', str(day_of_week))
            ], order='hour_from')

            if not work_hours:
                attendance.working_hours = total_hours
                attendance.regular_hours = total_hours
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
    
    @api.depends('working_hours', 'employee_id.resource_calendar_id')
    def _compute_overtime_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out and attendance.employee_id.resource_calendar_id:
                # Initialiser les heures
                standard_hours = 8.0  # Valeur par défaut
                
                # Vérifier si c'est un jour férié
                is_holiday = self.env['resource.calendar.leaves'].search([
                    ('calendar_id', '=', attendance.employee_id.resource_calendar_id.id),
                    ('date_from', '<=', attendance.check_in),
                    ('date_to', '>=', attendance.check_out)
                ], limit=1)
                
                if is_holiday:
                    # Toutes les heures sont supplémentaires si c'est un jour férié
                    attendance.overtime_hours = attendance.working_hours
                    continue

                # Vérifier si c'est un weekend
                is_weekend = attendance.check_in.weekday() in (5, 6)  # 5=Samedi, 6=Dimanche
                if is_weekend:
                    # Toutes les heures sont supplémentaires le weekend
                    attendance.overtime_hours = attendance.working_hours
                    continue
                
                # Jour normal : calculer les heures standard depuis le calendrier
                calendar = attendance.employee_id.resource_calendar_id
                day_of_week = attendance.check_in.weekday()
                
                # Recherche des horaires de travail pour ce jour
                work_hours = self.env['resource.calendar.attendance'].search([
                    ('calendar_id', '=', calendar.id),
                    ('dayofweek', '=', str(day_of_week))
                ])
                
                if work_hours:
                    # Calculer les heures standard en tenant compte des pauses
                    total_hours = 0
                    for line in work_hours:
                        total_hours += line.hour_to - line.hour_from
                        if total_hours > 4:  # Pause déjeuner après 4h de travail
                            total_hours -= 1  # 1h de pause déjeuner
                    standard_hours = total_hours
                
                # Calculer les heures supplémentaires
                if attendance.working_hours > standard_hours:
                    attendance.overtime_hours = attendance.working_hours - standard_hours
                else:
                    attendance.overtime_hours = 0.0
            else:
                attendance.overtime_hours = 0.0
    
    @api.depends('check_in', 'check_out', 'employee_id.resource_calendar_id')
    def _compute_attendance_types(self):
        for attendance in self:
            attendance_type_ids = self.env['pointeur_hr.attendance.type']
            
            if not attendance.check_in or not attendance.check_out:
                attendance.attendance_type_ids = attendance_type_ids
                continue
                
            # Obtenir le calendrier de travail de l'employé
            calendar = attendance.employee_id.resource_calendar_id
            if not calendar:
                attendance.attendance_type_ids = attendance_type_ids
                continue
                
            # Déterminer le jour de la semaine
            day_of_week = attendance.check_in.weekday()
            
            # Rechercher les horaires de travail pour ce jour
            work_hours = self.env['resource.calendar.attendance'].search([
                ('calendar_id', '=', calendar.id),
                ('dayofweek', '=', str(day_of_week))
            ], order='hour_from')
            
            if not work_hours:
                # Jour non travaillé selon le calendrier
                attendance_type_ids |= self.env['pointeur_hr.attendance.type'].search([('code', '=', 'overtime')])
                attendance.attendance_type_ids = attendance_type_ids
                continue
                
            # Obtenir l'heure de début et de fin prévue
            start_hour = min(work_hours.mapped('hour_from'))
            end_hour = max(work_hours.mapped('hour_to'))
            
            # Convertir les heures flottantes en heures et minutes
            start_time = self._float_to_time(start_hour)
            end_time = self._float_to_time(end_hour)
            
            # Obtenir l'heure d'arrivée et de départ
            check_in_time = attendance.check_in.time()
            check_out_time = attendance.check_out.time()
            
            # Marge de tolérance (en minutes)
            tolerance_minutes = 15
            tolerance = timedelta(minutes=tolerance_minutes)
            
            # Vérifier si l'employé est arrivé en retard
            if check_in_time > (datetime.combine(datetime.min.date(), start_time) + tolerance).time():
                attendance_type_ids |= self.env['pointeur_hr.attendance.type'].search([('code', '=', 'late')])
            
            # Vérifier si l'employé est parti tôt
            if check_out_time < (datetime.combine(datetime.min.date(), end_time) - tolerance).time():
                attendance_type_ids |= self.env['pointeur_hr.attendance.type'].search([('code', '=', 'early_leave')])
            
            # Vérifier les heures supplémentaires
            if attendance.overtime_hours > 0:
                attendance_type_ids |= self.env['pointeur_hr.attendance.type'].search([('code', '=', 'overtime')])
            
            attendance.attendance_type_ids = attendance_type_ids
    
    def _float_to_time(self, float_hour):
        """Convertit une heure flottante (ex: 7.5) en objet time (07:30:00)"""
        hours = int(float_hour)
        minutes = int((float_hour - hours) * 60)
        return time(hours, minutes)
