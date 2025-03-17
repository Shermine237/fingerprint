from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

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
                    'warning': {
                        'title': 'Attention',
                        'message': 'Veuillez sélectionner au moins une ligne à exporter.'
                    }
                }
            records = Report.browse(active_ids)
        else:
            # Tout exporter en utilisant les filtres actuels
            try:
                # Récupérer le domaine de l'action principale
                action = self.env.ref('pointeur_hr.pointeur_hr_action_hr_attendance_report')
                domain = action.domain or []
                
                # Appliquer le domaine en ignorant les active_ids
                ctx = dict(self._context)
                ctx.pop('active_ids', None)
                ctx.pop('active_id', None)
                ctx.pop('active_model', None)
                
                records = Report.with_context(**ctx).search(domain)
            except Exception as e:
                _logger.error(f"Erreur lors de l'application du domaine: {e}")
                # En cas d'erreur, récupérer toutes les lignes
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
