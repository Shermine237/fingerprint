from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta


class PointeurHrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    # Fields for import
    import_id = fields.Many2one('pointeur_hr.import', string='Import', readonly=True)
    
    # Additional fields for attendance
    default_location_id = fields.Many2one('pointeur_hr.location', string='Default Attendance Location',
                                        help="Employee's default attendance location")
    badge_id = fields.Char(string='Badge ID', help="Employee's unique badge identifier")
    
    # Attendance statistics
    attendance_rate = fields.Float(string='Attendance Rate', compute='_compute_attendance_stats', store=True)
    total_overtime_hours = fields.Float(string='Total Overtime Hours', compute='_compute_attendance_stats', store=True)
    total_late_count = fields.Integer(string='Number of Late Arrivals', compute='_compute_attendance_stats', store=True)
    total_early_leave_count = fields.Integer(string='Number of Early Departures', compute='_compute_attendance_stats', store=True)
    
    @api.depends('attendance_ids')
    def _compute_attendance_stats(self):
        """Compute attendance statistics"""
        for employee in self:
            # Calculate the first day of the current month
            today = date.today()
            start_date = today.replace(day=1)
            
            # Get valid attendances for the current month
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', start_date.strftime('%Y-%m-%d')),
                ('check_in', '<=', today.strftime('%Y-%m-%d 23:59:59')),
                ('check_in', '!=', False)  # Ignore lines without check_in
            ])

            # Initialize counters
            total_days = 0
            overtime_hours = 0
            late_count = 0
            early_leave_count = 0

            # Calculate statistics
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

            # Calculate attendance rate (days of presence / working days)
            working_days = self._get_working_days(start_date, today)
            employee.attendance_rate = (total_days / working_days) * 100 if working_days > 0 else 0
            employee.total_overtime_hours = overtime_hours
            employee.total_late_count = late_count
            employee.total_early_leave_count = early_leave_count

    def _get_working_days(self, start_date, end_date):
        """Calculate the number of working days between two dates"""
        # For simplicity, we consider 22 working days per month
        return 22

    def action_view_attendances(self):
        """View employee's attendances"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_attendance.hr_attendance_action")
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'search_default_today': 1}
        return action

    def action_view_overtime(self):
        """View employee's overtime"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("hr_attendance.hr_attendance_action")
        action['domain'] = [
            ('employee_id', '=', self.id),
            ('attendance_type_ids', 'ilike', 'supplementaire')
        ]
        action['context'] = {'search_default_today': 1}
        return action
