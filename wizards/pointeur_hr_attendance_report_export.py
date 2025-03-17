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
        ('all', 'Tout exporter (filtrage actuel)')
    ], string='Portée de l\'export', required=True, default='selected',
        help='Choisissez d\'exporter uniquement les lignes sélectionnées ou toutes les lignes en utilisant les filtres de recherche actuels')

    def action_export(self):
        """Export le rapport dans le format sélectionné"""
        Report = self.env['pointeur_hr.attendance.report']
        
        if self.export_scope == 'selected':
            # Par défaut : exporter uniquement les lignes sélectionnées
            records = Report.browse(self._context.get('active_ids', []))
        else:
            # Tout exporter en utilisant les filtres de recherche actuels
            # On crée un nouveau contexte sans les active_ids pour éviter de filtrer sur la sélection
            ctx = dict(self._context)
            if 'active_ids' in ctx:
                del ctx['active_ids']
            if 'active_id' in ctx:
                del ctx['active_id']
            records = Report.with_context(**ctx).search([])

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
