from odoo import api, fields, models
import logging
from datetime import datetime

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
        ('all', 'Tout exporter (par date)')
    ], string='Portée de l\'export', required=True, default='selected')

    date_from = fields.Date(string='Date de début')
    date_to = fields.Date(string='Date de fin')

    @api.onchange('export_scope')
    def _onchange_export_scope(self):
        if self.export_scope == 'all':
            # Initialiser avec le mois en cours
            today = datetime.today()
            self.date_from = datetime(today.year, today.month, 1).date()
            self.date_to = datetime(today.year, today.month + 1, 1).date() if today.month < 12 else datetime(today.year + 1, 1, 1).date()
        else:
            self.date_from = False
            self.date_to = False

    def action_export(self):
        """Export le rapport dans le format sélectionné"""
        Report = self.env['pointeur_hr.attendance.report']
        
        if self.export_scope == 'selected':
            # Exporter uniquement les lignes sélectionnées (code inchangé)
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
            # Vérifier les dates
            if not self.date_from or not self.date_to:
                return {
                    'warning': {
                        'title': 'Attention',
                        'message': 'Veuillez spécifier les dates de début et de fin.'
                    }
                }
            
            # Rechercher toutes les lignes dans l'intervalle de date
            domain = [
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to)
            ]
            
            # Récupérer et trier les enregistrements par nom d'employé
            records = Report.search(domain, order='employee_id')

        if not records:
            return {
                'warning': {
                    'title': 'Attention',
                    'message': 'Aucune ligne à exporter pour la période sélectionnée.'
                }
            }

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
