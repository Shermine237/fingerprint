from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'
    
    # Champs additionnels pour le pointage
    location_id = fields.Many2one('pointeur.location', string='Lieu de pointage')
    attendance_type = fields.Selection([
        ('normal', 'Normal'),
        ('overtime', 'Heures supplémentaires'),
        ('late', 'Retard'),
        ('early_leave', 'Départ anticipé')
    ], string='Type de présence', default='normal', compute='_compute_attendance_type', store=True)
    notes = fields.Text(string='Notes')
    
    # Champs calculés
    working_hours = fields.Float(string='Heures travaillées', compute='_compute_working_hours', store=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', compute='_compute_overtime_hours', store=True)
    
    @api.depends('check_in', 'check_out')
    def _compute_working_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                delta = attendance.check_out - attendance.check_in
                attendance.working_hours = delta.total_seconds() / 3600.0
            else:
                attendance.working_hours = 0.0
    
    @api.depends('working_hours', 'employee_id.resource_calendar_id')
    def _compute_overtime_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out and attendance.employee_id.resource_calendar_id:
                # Récupérer les heures standard de travail pour l'employé
                standard_hours = 8.0  # Valeur par défaut
                
                # Vérifier si l'employé a un calendrier de travail défini
                if attendance.employee_id.resource_calendar_id:
                    # Logique pour calculer les heures standard basées sur le calendrier
                    # Cette logique peut être plus complexe selon les besoins
                    day_of_week = attendance.check_in.weekday()
                    calendar = attendance.employee_id.resource_calendar_id
                    
                    # Recherche des horaires de travail pour ce jour
                    work_hours = self.env['resource.calendar.attendance'].search([
                        ('calendar_id', '=', calendar.id),
                        ('dayofweek', '=', str(day_of_week))
                    ])
                    
                    if work_hours:
                        # Calculer les heures standard pour ce jour
                        standard_hours = sum((line.hour_to - line.hour_from) for line in work_hours)
                
                # Calculer les heures supplémentaires
                if attendance.working_hours > standard_hours:
                    attendance.overtime_hours = attendance.working_hours - standard_hours
                else:
                    attendance.overtime_hours = 0.0
            else:
                attendance.overtime_hours = 0.0
    
    @api.depends('check_in', 'check_out', 'employee_id.resource_calendar_id')
    def _compute_attendance_type(self):
        for attendance in self:
            attendance_type = 'normal'
            
            if not attendance.check_in or not attendance.check_out:
                attendance.attendance_type = 'normal'
                continue
                
            # Obtenir le calendrier de travail de l'employé
            calendar = attendance.employee_id.resource_calendar_id
            if not calendar:
                attendance.attendance_type = 'normal'
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
                attendance.attendance_type = 'overtime'
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
            if check_in_time > (datetime.combine(datetime.min, start_time) + tolerance).time():
                attendance_type = 'late'
            
            # Vérifier si l'employé est parti tôt
            if check_out_time < (datetime.combine(datetime.min, end_time) - tolerance).time():
                # Si déjà en retard, on garde le statut 'late'
                if attendance_type != 'late':
                    attendance_type = 'early_leave'
            
            # Vérifier les heures supplémentaires
            if attendance.overtime_hours > 0:
                # Priorité aux heures supplémentaires si l'employé a fait plus que ses heures standard
                attendance_type = 'overtime'
            
            attendance.attendance_type = attendance_type
    
    def _float_to_time(self, float_hour):
        """Convertit une heure flottante (ex: 7.5) en objet time (07:30:00)"""
        hours = int(float_hour)
        minutes = int((float_hour - hours) * 60)
        return datetime.time(hours, minutes)


class PointeurLocation(models.Model):
    _name = 'pointeur.location'
    _description = 'Lieu de pointage'
    
    name = fields.Char(string='Nom', required=True)
    address = fields.Text(string='Adresse')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    notes = fields.Text(string='Notes')
