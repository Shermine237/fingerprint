from odoo import api, fields, models

class PointeurHrAttendanceReportExport(models.TransientModel):
    _name = 'pointeur_hr.attendance.report.export.wizard'
    _description = 'Assistant d\'export du rapport de présence'

    export_type = fields.Selection([
        ('excel', 'Excel'),
        ('pdf', 'PDF')
    ], string='Type d\'export', required=True, default='excel')

    def action_export(self):
        """Export le rapport dans le format sélectionné"""
        active_ids = self.env.context.get('active_ids', [])
        records = self.env['pointeur_hr.attendance.report']
        
        # Si des lignes sont sélectionnées, exporter uniquement ces lignes
        if active_ids:
            records = records.browse(active_ids)
        else:
            # Sinon, exporter toutes les lignes avec les filtres actuels
            domain = self.env.context.get('search_domain', [])
            records = records.search(domain)

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
