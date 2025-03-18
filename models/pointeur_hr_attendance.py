from odoo import models, fields, api
from datetime import datetime, timedelta
from pytz import timezone, UTC
from odoo.exceptions import ValidationError


class PointeurHrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Champs de base
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    import_id = fields.Many2one('pointeur_hr.import', string='Import source')
    import_line_id = fields.Many2one('pointeur_hr.import.line', string='Ligne d\'import')
    source = fields.Selection([
        ('manual', 'Manuel'),
        ('import', 'Import')
    ], string='Source', default='manual', required=True)

    # Champs calculés
    working_hours = fields.Float(string='Heures travaillées', compute='_compute_working_hours', store=True)
    regular_hours = fields.Float(string='Heures normales', compute='_compute_working_hours', store=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', compute='_compute_working_hours', store=True)
    late_hours = fields.Float(string='Retard', compute='_compute_working_hours', store=True)
    early_leave_hours = fields.Float(string='Départ anticipé', compute='_compute_working_hours', store=True)
    attendance_type_ids = fields.Char(string='Types de présence', compute='_compute_working_hours', store=True)

    @api.constrains('check_in', 'check_out')
    def _check_validity(self):
        """Vérifie que l'heure de sortie est après l'heure d'entrée et qu'il y a bien une heure d'entrée"""
        for attendance in self:
            if attendance.check_out and not attendance.check_in:
                raise ValidationError(_("Une présence ne peut pas avoir une heure de sortie sans heure d'entrée."))
            if attendance.check_in and attendance.check_out and attendance.check_in > attendance.check_out:
                raise ValidationError(_("L'heure de sortie doit être après l'heure d'entrée."))

    @api.depends('check_in', 'check_out')
    def _compute_working_hours(self):
        for attendance in self:
            if not attendance.check_in or not attendance.check_out:
                attendance.working_hours = 0.0
                attendance.regular_hours = 0.0
                attendance.overtime_hours = 0.0
                attendance.late_hours = 0.0
                attendance.early_leave_hours = 0.0
                attendance.attendance_type_ids = ''
                continue

            # Calcul des heures travaillées
            delta = attendance.check_out - attendance.check_in
            attendance.working_hours = delta.total_seconds() / 3600.0

            # Récupération des horaires de travail
            employee = attendance.employee_id
            calendar = employee.resource_calendar_id
            if not calendar:
                calendar = self.env.company.resource_calendar_id

            # Convertir les dates en UTC avec fuseau horaire
            tz = timezone(calendar.tz or self.env.user.tz or 'UTC')
            start_dt = attendance.check_in.replace(hour=0, minute=0, second=0).astimezone(tz)
            end_dt = attendance.check_in.replace(hour=23, minute=59, second=59).astimezone(tz)

            # Obtenir les horaires prévus pour ce jour
            intervals = calendar._work_intervals_batch(
                start_dt,
                end_dt,
                resources=employee.resource_id,
                tz=tz
            )[employee.resource_id.id]

            # Convertir les intervalles en liste
            interval_list = list(intervals)
            if not interval_list:
                # Jour non travaillé
                attendance.overtime_hours = attendance.working_hours
                attendance.regular_hours = 0.0
                attendance.late_hours = 0.0
                attendance.early_leave_hours = 0.0
                if attendance.working_hours > 0:
                    attendance.attendance_type_ids = 'supplementaire'
                else:
                    attendance.attendance_type_ids = ''
                continue

            # Récupérer le premier intervalle de travail de la journée
            work_start = interval_list[0][0]
            work_end = interval_list[-1][1]
            work_hours = sum(
                (stop - start).total_seconds() / 3600
                for start, stop, meta in interval_list
            )

            # Calcul des heures normales et supplémentaires
            attendance.regular_hours = min(attendance.working_hours, work_hours)
            attendance.overtime_hours = max(0.0, attendance.working_hours - work_hours)

            # Calcul du retard
            check_in_tz = attendance.check_in.astimezone(tz)
            if check_in_tz > work_start:
                delta = check_in_tz - work_start
                attendance.late_hours = delta.total_seconds() / 3600.0
            else:
                attendance.late_hours = 0.0

            # Calcul du départ anticipé
            check_out_tz = attendance.check_out.astimezone(tz)
            if check_out_tz < work_end:
                delta = work_end - check_out_tz
                attendance.early_leave_hours = delta.total_seconds() / 3600.0
            else:
                attendance.early_leave_hours = 0.0

            # Détermination des types de présence
            types = []
            if attendance.overtime_hours > 0:
                types.append('supplementaire')
            if attendance.late_hours > 0:
                types.append('retard')
            if attendance.early_leave_hours > 0:
                types.append('depart_anticipe')

            attendance.attendance_type_ids = ','.join(types) if types else ''
