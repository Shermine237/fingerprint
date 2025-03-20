from odoo import api, fields, models

class FingerprintHrAttendanceReportExport(models.TransientModel):
    _name = 'fingerprint_hr.attendance.report.export.wizard'
    _description = 'Attendance Report Export Wizard'

    export_type = fields.Selection([
        ('excel', 'Excel'),
        ('pdf', 'PDF')
    ], string='Export Type', required=True, default='excel')

    export_scope = fields.Selection([
        ('selected', 'Selected Lines'),
        ('all', 'Export All (current filters)')
    ], string='Export Scope', required=True, default='selected',
        help='Choose to export only selected lines or all lines using the current search filters')

    def action_export(self):
        """Export attendance report in the selected format"""
        Report = self.env['fingerprint_hr.attendance.report']
        
        if self.export_scope == 'selected':
            # Export only selected lines
            active_ids = self._context.get('active_ids', [])
            if not active_ids:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Attention',
                        'message': 'Please select at least one line to export.',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            records = Report.browse(active_ids)
        else:
            # Export all lines using current search filters
            records = Report.search([])

        if not records:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Attention',
                    'message': 'No lines to export.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
