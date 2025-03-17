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
        ('all', 'Tout exporter (filtres actuels)')
    ], string='Portée de l\'export', required=True, default='selected',
        help='Choisissez d\'exporter uniquement les lignes sélectionnées ou toutes les lignes en utilisant les filtres de recherche actuels')

    def action_export(self):
        """Export le rapport dans le format sélectionné"""
        Report = self.env['pointeur_hr.attendance.report']
        
        if self.export_scope == 'selected':
            # Exporter uniquement les lignes sélectionnées
            active_ids = self._context.get('active_ids', [])
            if not active_ids:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Attention',
                        'message': 'Veuillez sélectionner au moins une ligne à exporter.',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            records = Report.browse(active_ids)
        else:
            # Récupérer la liste filtrée en utilisant le contexte actuel
            # Supprimer les active_ids pour éviter de filtrer sur la sélection
            ctx = {k: v for k, v in self._context.items() if not k.startswith('active_')}
            records = Report.with_context(**ctx).search([])

        if not records:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Attention',
                    'message': 'Aucune ligne à exporter.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
