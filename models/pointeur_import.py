from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class PointeurImport(models.Model):
    _name = 'pointeur.import'
    _description = 'Import des données du pointeur physique'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom', required=True, default=lambda self: _('Import du %s') % fields.Date.context_today(self).strftime('%d/%m/%Y'))
    file = fields.Binary(string='Fichier CSV', required=True)
    filename = fields.Char(string='Nom du fichier')
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', 'Terminé'),
        ('error', 'Erreur')
    ], string='État', default='draft', tracking=True)

    def action_import(self):
        """Importer les données du fichier CSV"""
        self.ensure_one()

        if not self.file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))

        # Décodage du fichier CSV
        csv_data = base64.b64decode(self.file)
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)

        # Variables pour le suivi des erreurs
        error_lines = []
        success_count = 0

        for row in reader:
            try:
                # Recherche de l'employé
                employee = self.env['hr.employee'].search([('name', '=', row['Display Name'])], limit=1)
                if not employee:
                    error_lines.append(f"Employé non trouvé : {row['Display Name']}")
                    continue

                # Conversion des dates
                check_in = datetime.strptime(row['In Time'], '%Y-%m-%d %H:%M:%S')
                check_out = datetime.strptime(row['Out Time'], '%Y-%m-%d %H:%M:%S') if row['Out Time'] else False

                # Création de la présence
                attendance_vals = {
                    'employee_id': employee.id,
                    'check_in': check_in,
                    'check_out': check_out,
                    'source': 'import',  # Définition de la source comme 'import'
                }

                attendance = self.env['hr.attendance'].create(attendance_vals)
                success_count += 1

            except Exception as e:
                error_lines.append(f"Erreur lors du traitement de la ligne {reader.line_num}: {str(e)}")

        # Mise à jour du statut et des messages
        if error_lines:
            self.message_post(body=_("Erreurs d'importation:\n%s") % '\n'.join(error_lines))
        
        message = _("%d présences ont été importées avec succès.") % success_count
        if error_lines:
            message += _("\n%d erreurs ont été rencontrées.") % len(error_lines)
        
        self.message_post(body=message)
        self.state = 'done'
