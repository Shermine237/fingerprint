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
            # Récupérer l'action pour obtenir le domaine de recherche actuel
            action = self.env.ref('pointeur_hr.pointeur_hr_action_hr_attendance_report')
            if not action:
                # Si l'action n'est pas trouvée, on exporte tout
                records = Report.search([])
            else:
                # Exécuter l'action pour obtenir le domaine actuel
                action_result = action.read()[0]
                domain = action_result.get('domain', [])
                
                # Créer un contexte sans les active_ids
                ctx = dict(self.env.context)
                ctx.pop('active_ids', None)
                ctx.pop('active_id', None)
                ctx.pop('active_model', None)
                
                # Rechercher avec le domaine actuel mais sans les active_ids
                records = Report.with_context(**ctx).search(domain)

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
