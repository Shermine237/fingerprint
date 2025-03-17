from odoo import api, fields, models
import ast

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
            # Par défaut : exporter uniquement les lignes sélectionnées
            active_ids = self._context.get('active_ids', [])
            if not active_ids:
                return {
                    'warning': {
                        'title': 'Attention',
                        'message': 'Veuillez sélectionner au moins une ligne à exporter.'
                    }
                }
            records = Report.browse(active_ids)
        else:
            # Tout exporter en utilisant les filtres de recherche actuels
            # On crée un nouvel environnement sans les active_ids
            ctx = {}
            # Conserver uniquement les filtres de recherche
            for key, value in self._context.items():
                if key.startswith('search_') or key == 'group_by':
                    ctx[key] = value
            
            # Rechercher toutes les lignes avec les filtres actuels
            records = Report.with_context(**ctx).search([])
            
            # Si aucun filtre n'est appliqué, récupérer toutes les lignes
            if not records:
                records = Report.search([])

        if not records:
            return {
                'warning': {
                    'title': 'Attention',
                    'message': 'Aucune ligne à exporter.'
                }
            }

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
