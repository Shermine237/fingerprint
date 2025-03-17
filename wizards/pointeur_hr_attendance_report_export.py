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
            # Obtenir la vue actuelle et son domaine
            action = self.env.ref('pointeur_hr.pointeur_hr_action_hr_attendance_report')
            action_dict = action.read()[0] if action else {}
            
            # Créer un nouveau contexte sans active_ids mais en conservant les filtres
            new_ctx = {}
            # Conserver les filtres de recherche
            for key, value in self._context.items():
                if key.startswith('search_') or key == 'group_by':
                    new_ctx[key] = value
            
            # Essai 1: Utiliser action.search_view_id
            if action.search_view_id:
                try:
                    search_view = action.search_view_id.read(['domain'])[0]
                    domain = search_view.get('domain', [])
                    if domain:
                        records = Report.with_context(**new_ctx).search(domain)
                        if records:
                            return self._process_export(records)
                except Exception as e:
                    _logger.error(f"Erreur lors de la récupération du domaine de la vue de recherche: {e}")
            
            # Essai 2: Utiliser le domaine de l'action
            try:
                domain = action_dict.get('domain', [])
                if domain:
                    records = Report.with_context(**new_ctx).search(domain)
                    if records:
                        return self._process_export(records)
            except Exception as e:
                _logger.error(f"Erreur lors de la recherche avec le domaine de l'action: {e}")
                
            # Essai 3: Utiliser search_default_ du contexte pour créer un domaine
            domain = []
            for key, value in self._context.items():
                if key.startswith('search_default_') and value:
                    field = key.replace('search_default_', '')
                    if field in Report._fields:
                        domain.append((field, '=', value))
            
            if domain:
                records = Report.with_context(**new_ctx).search(domain)
                if records:
                    return self._process_export(records)
            
            # Solution de secours: exporter toutes les lignes
            records = Report.search([])

        return self._process_export(records)
    
    def _process_export(self, records):
        """Traite l'export des enregistrements"""
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
