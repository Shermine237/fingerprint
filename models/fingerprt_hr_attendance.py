from odoo import models, fields, api, _
from datetime import datetime, timedelta
from pytz import timezone, UTC
from odoo.exceptions import ValidationError


class FingerprtHrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Base fields
    location_id = fields.Many2one('fingerprt_hr.location', string='Attendance Location')
    import_id = fields.Many2one('fingerprt_hr.import', string='Source Import')
    import_line_id = fields.Many2one('fingerprt_hr.import.line', string='Import Line')
    source = fields.Selection([
        ('manual', 'Manual'),
        ('import', 'Import')
    ], string='Source', default='manual', required=True)

    # Calculated fields
    working_hours = fields.Float(string='Working Hours', compute='_compute_working_hours', store=True)
    regular_hours = fields.Float(string='Regular Hours', compute='_compute_working_hours', store=True)
    overtime_hours = fields.Float(string='Overtime Hours', compute='_compute_working_hours', store=True)
    late_hours = fields.Float(string='Late Hours', compute='_compute_working_hours', store=True)
    early_leave_hours = fields.Float(string='Early Leave Hours', compute='_compute_working_hours', store=True)
    attendance_type_ids = fields.Char(string='Attendance Types', compute='_compute_working_hours', store=True)

    @api.model
    def create(self, vals):
        """Override the create method to ensure the source is correctly defined"""
        # If the record comes from an import, ensure the source is 'import'
        if vals.get('import_id') or vals.get('import_line_id'):
            vals['source'] = 'import'
        return super(FingerprtHrAttendance, self).create(vals)

    @api.constrains('check_in', 'check_out')
    def _check_validity(self):
        """Ensure check-out time is after check-in time and there is a check-in time"""
        for attendance in self:
            if attendance.check_out and not attendance.check_in:
                raise ValidationError(_("An attendance cannot have a check-out time without a check-in time."))
            if attendance.check_in and attendance.check_out and attendance.check_in > attendance.check_out:
                raise ValidationError(_("Check-out time must be after check-in time."))

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

            # Calculate working hours
            delta = attendance.check_out - attendance.check_in
            attendance.working_hours = delta.total_seconds() / 3600.0

            # Get working hours
            employee = attendance.employee_id
            calendar = employee.resource_calendar_id
            if not calendar:
                calendar = self.env.company.resource_calendar_id

            # Convert dates to UTC with timezone
            tz = timezone(calendar.tz or self.env.user.tz or 'UTC')
            start_dt = attendance.check_in.replace(hour=0, minute=0, second=0).astimezone(tz)
            end_dt = attendance.check_in.replace(hour=23, minute=59, second=59).astimezone(tz)

            # Get working hours
            intervals = calendar._work_intervals_batch(
                start_dt,
                end_dt,
                resources=employee.resource_id,
                tz=tz
            )[employee.resource_id.id]

            # Convert intervals to list
            interval_list = list(intervals)
            if not interval_list:
                # Day off
                attendance.overtime_hours = attendance.working_hours
                attendance.regular_hours = 0.0
                attendance.late_hours = 0.0
                attendance.early_leave_hours = 0.0
                if attendance.working_hours > 0:
                    attendance.attendance_type_ids = 'overtime'
                else:
                    attendance.attendance_type_ids = ''
                continue

            # Get first working interval of the day
            work_start = interval_list[0][0]
            work_end = interval_list[-1][1]
            work_hours = sum(
                (stop - start).total_seconds() / 3600
                for start, stop, meta in interval_list
            )

            # Calculate regular and overtime hours
            attendance.regular_hours = min(attendance.working_hours, work_hours)
            attendance.overtime_hours = max(0.0, attendance.working_hours - work_hours)

            # Calculate tardiness
            check_in_tz = attendance.check_in.astimezone(tz)
            if check_in_tz > work_start:
                delta = check_in_tz - work_start
                attendance.late_hours = delta.total_seconds() / 3600.0
            else:
                attendance.late_hours = 0.0

            # Calculate early departure
            check_out_tz = attendance.check_out.astimezone(tz)
            if check_out_tz < work_end:
                delta = work_end - check_out_tz
                attendance.early_leave_hours = delta.total_seconds() / 3600.0
            else:
                attendance.early_leave_hours = 0.0

            # Determine attendance types
            types = []
            if attendance.overtime_hours > 0:
                types.append('overtime')
            if attendance.late_hours > 0:
                types.append('late')
            if attendance.early_leave_hours > 0:
                types.append('early_leave')

            attendance.attendance_type_ids = ','.join(types) if types else ''
