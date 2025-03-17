from odoo import api, fields, models

class PointeurHrAttendanceReportExport(models.TransientModel):
    _name = 'pointeur_hr.attendance.report.export.wizard'
    _description = 'Assistant d\'export du rapport de présence'

    export_type = fields.Selection([
        ('excel', 'Excel'),
        ('pdf', 'PDF')
    ], string='Type d\'export', required=True, default='excel')

    export_scope = fields.Selection([
        ('selected', 'Lignes sélectionnées'),
        ('all', 'Tout exporter')
    ], string='Portée de l\'export', required=True, default='selected')

    def action_export(self):
        """Export le rapport dans le format sélectionné"""
        active_ids = self.env.context.get('active_ids', [])
        records = self.env['pointeur_hr.attendance.report']
        
        # Si on veut tout exporter ou s'il n'y a pas de lignes sélectionnées
        if self.export_scope == 'all':
            # Exporter toutes les lignes avec les filtres actuels
            domain = self.env.context.get('search_domain', [])
            records = records.search(domain)
        else:
            # Sinon, exporter uniquement les lignes sélectionnées
            records = records.browse(active_ids)

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
