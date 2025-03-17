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
            # Approche hybride: on utilise une requête SQL directe pour récupérer tous les IDs
            # mais on applique les filtres de recherche actuels si possible
            try:
                # Récupérer les filtres de recherche actuels
                domain = []
                for key, value in self._context.items():
                    if key.startswith('search_default_'):
                        field_name = key.replace('search_default_', '')
                        if hasattr(Report, field_name) and value:
                            domain.append((field_name, '=', value))
                
                # Si des filtres sont trouvés, les appliquer
                if domain:
                    # Créer un contexte sans active_ids
                    ctx = dict(self._context)
                    ctx.pop('active_ids', None)
                    ctx.pop('active_id', None)
                    ctx.pop('active_model', None)
                    
                    records = Report.with_context(**ctx).search(domain)
                else:
                    # Sinon, récupérer toutes les lignes
                    self.env.cr.execute("SELECT id FROM pointeur_hr_attendance_report")
                    all_ids = [r[0] for r in self.env.cr.fetchall()]
                    records = Report.browse(all_ids)
            except Exception as e:
                _logger.error(f"Erreur lors de l'application des filtres: {e}")
                # En cas d'erreur, récupérer toutes les lignes
                self.env.cr.execute("SELECT id FROM pointeur_hr_attendance_report")
                all_ids = [r[0] for r in self.env.cr.fetchall()]
                records = Report.browse(all_ids)

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
