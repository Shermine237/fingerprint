from odoo import api, fields, models, tools, _
from datetime import datetime, timedelta
import pytz
import base64
import xlsxwriter
import io

class PointeurHrAttendanceReport(models.Model):
    _name = 'pointeur_hr.attendance.report'
    _description = 'Attendance Report'
    _auto = False
    _order = 'date desc, employee_id'

    name = fields.Char(string='Name', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    location_id = fields.Many2one('pointeur_hr.location', string='Attendance Location', readonly=True)
    default_location_id = fields.Many2one('pointeur_hr.location', string='Default Location', readonly=True)
    source = fields.Selection([
        ('manual', 'Manual'),
        ('import', 'Import')
    ], string='Source', readonly=True)
    check_in = fields.Datetime(string='Check In', readonly=True)
    check_out = fields.Datetime(string='Check Out', readonly=True)
    attendance_type_ids = fields.Char(string='Attendance Types', readonly=True)
    working_hours = fields.Float(string='Working Hours', readonly=True)
    regular_hours = fields.Float(string='Regular Hours', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)
    late_hours = fields.Float(string='Late Hours', readonly=True)
    early_leave_hours = fields.Float(string='Early Leave Hours', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Check if default_location_id column exists in hr_employee
        self.env.cr.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'hr_employee' 
            AND column_name = 'default_location_id'
        """)
        has_default_location = bool(self.env.cr.fetchone())

        # Build query based on column existence
        default_location_field = "e.default_location_id" if has_default_location else "NULL"
        
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
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
                FROM hr_attendance a
                JOIN hr_employee e ON e.id = a.employee_id
            )
        """ % (self._table, default_location_field))

    def _get_records_to_export(self):
        """Return records to export based on context"""
        active_ids = self._context.get('active_ids')
        if active_ids:
            # If lines are selected, export only these lines
            return self.browse(active_ids)
        # Otherwise, export all lines with current filters
        return self.search(self._context.get('search_domain', []))

    def action_export_xlsx(self):
        """Export attendance reports to Excel file"""
        records = self._get_records_to_export()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Attendance Report')

        # Styles
        header_style = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D3D3D3',
            'border': 1
        })
        cell_style = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        time_style = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '[h]:mm'
        })

        # Headers
        headers = [
            'Date', 'Employee', 'Department', 'Default Location', 'Attendance Location',
            'Source', 'Check In', 'Check Out', 'Attendance Types', 'Working Hours',
            'Regular Hours', 'Overtime Hours', 'Late Hours', 'Early Leave Hours'
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_style)
            worksheet.set_column(col, col, 15)

        # Data
        row = 1
        for record in records:
            worksheet.write(row, 0, record.date.strftime('%d/%m/%Y'), cell_style)
            worksheet.write(row, 1, record.employee_id.name, cell_style)
            worksheet.write(row, 2, record.department_id.name or '', cell_style)
            worksheet.write(row, 3, record.default_location_id.name or '', cell_style)
            worksheet.write(row, 4, record.location_id.name or '', cell_style)
            worksheet.write(row, 5, dict(self._fields['source'].selection).get(record.source), cell_style)
            worksheet.write(row, 6, record.check_in.strftime('%H:%M') if record.check_in else '', cell_style)
            worksheet.write(row, 7, record.check_out.strftime('%H:%M') if record.check_out else '', cell_style)
            worksheet.write(row, 8, record.attendance_type_ids.replace(',', ', ') if record.attendance_type_ids else '', cell_style)
            worksheet.write(row, 9, record.working_hours, time_style)
            worksheet.write(row, 10, record.regular_hours, time_style)
            worksheet.write(row, 11, record.overtime_hours, time_style)
            worksheet.write(row, 12, record.late_hours, time_style)
            worksheet.write(row, 13, record.early_leave_hours, time_style)
            row += 1

        workbook.close()

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'Attendance_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            'datas': base64.b64encode(output.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Return action to download file
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_export_pdf(self):
        """Export attendance reports to PDF file"""
        records = self._get_records_to_export()
        # Return action to generate PDF
        return self.env.ref('pointeur_hr.action_report_attendance').report_action(records)
