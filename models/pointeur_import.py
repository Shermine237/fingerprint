from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class PointeurImport(models.Model):
    _name = 'pointeur_hr.import'
    _description = 'Import des données du pointeur physique'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom', required=True, default=lambda self: _('Import du %s') % fields.Date.context_today(self).strftime('%d/%m/%Y'))
    file = fields.Binary(string='Fichier CSV', required=True)
    filename = fields.Char(string='Nom du fichier')
    import_date = fields.Datetime(string='Date d\'import', readonly=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    line_count = fields.Integer(string='Nombre de lignes', compute='_compute_line_count')
    attendance_count = fields.Integer(string='Nombre de présences', compute='_compute_attendance_count')
    
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('imported', 'Importé'),
        ('done', 'Terminé'),
        ('cancelled', 'Annulé'),
        ('error', 'Erreur')
    ], string='État', default='draft', tracking=True)

    line_ids = fields.One2many('pointeur_hr.import.line', 'import_id', string='Lignes importées')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends('line_ids.attendance_id')
    def _compute_attendance_count(self):
        for record in self:
            record.attendance_count = len(record.line_ids.filtered(lambda l: l.attendance_id))

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

        # Suppression des anciennes lignes
        self.line_ids.unlink()

        for row in reader:
            try:
                # Conversion des dates et heures
                date = datetime.strptime(row['Date'], '%m/%d/%y').date()
                in_time = datetime.strptime(f"{row['Date']} {row['In Time']}", '%m/%d/%y %I:%M%p')
                out_time = None
                if row['Out Time'] and row['Out Day']:
                    # Convertir l'heure de sortie
                    out_time = datetime.strptime(f"{date.strftime('%m/%d/%y')} {row['Out Time']}", '%m/%d/%y %I:%M%p')
                    # Si la sortie est le lendemain, ajouter un jour
                    if row['Out Day'] != row['In Day']:
                        out_time += timedelta(days=1)

                vals = {
                    'import_id': self.id,
                    'display_name': row['Display Name'],
                    'display_id': row['Display ID'],
                    'payroll_id': row.get('Payroll ID', ''),
                    'date': date,
                    'in_day': row['In Day'],
                    'in_time': row['In Time'],
                    'out_day': row['Out Day'],
                    'out_time': row['Out Time'],
                    'check_in': in_time,
                    'check_out': out_time,
                    'department': row['Department'],
                    'dept_code': row['Dept. Code'],
                    'reg_hours': float(row.get('REG', 0)),
                    'ot1_hours': float(row.get('OT1', 0)),
                    'ot2_hours': float(row.get('OT2', 0)),
                    'total_hours': float(row.get('Total', 0)),
                    'in_note': row.get('In Note', ''),
                    'out_note': row.get('Out Note', '')
                }
                self.env['pointeur_hr.import.line'].create(vals)
                success_count += 1

            except Exception as e:
                error_lines.append(f"Erreur lors du traitement de la ligne {reader.line_num}: {str(e)}")

        # Mise à jour du statut et des messages
        if error_lines:
            self.message_post(body=_("Erreurs d'importation:\n%s") % '\n'.join(error_lines))
            self.state = 'error'
        else:
            message = _("%d lignes ont été importées avec succès.") % success_count
            self.message_post(body=message)
            self.state = 'imported'
            self.import_date = fields.Datetime.now()

    def action_create_attendances(self):
        """Créer les présences à partir des lignes importées"""
        self.ensure_one()

        if self.state != 'imported':
            raise UserError(_("Les présences ne peuvent être créées qu'à partir d'un import validé."))

        for line in self.line_ids:
            if not line.attendance_id:
                try:
                    # Recherche de l'employé
                    employee = self.env['hr.employee'].search([('name', '=', line.display_name)], limit=1)
                    if not employee:
                        line.state = 'error'
                        line.error_message = f"Employé non trouvé : {line.display_name}"
                        continue

                    # Création de la présence
                    attendance_vals = {
                        'employee_id': employee.id,
                        'check_in': line.check_in,
                        'check_out': line.check_out,
                        'source': 'import',
                    }
                    attendance = self.env['hr.attendance'].create(attendance_vals)
                    line.write({
                        'attendance_id': attendance.id,
                        'state': 'done'
                    })

                except Exception as e:
                    line.write({
                        'state': 'error',
                        'error_message': str(e)
                    })

        # Mise à jour du statut
        if all(line.state == 'done' for line in self.line_ids):
            self.state = 'done'
            self.message_post(body=_("Toutes les présences ont été créées avec succès."))
        else:
            error_count = len(self.line_ids.filtered(lambda l: l.state == 'error'))
            self.message_post(body=_("%d erreurs ont été rencontrées lors de la création des présences.") % error_count)

    def action_view_attendances(self):
        """Voir les présences créées"""
        self.ensure_one()
        attendances = self.line_ids.mapped('attendance_id')
        action = {
            'name': _('Présences'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
        }
        return action

    def action_cancel(self):
        """Annuler l'import"""
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset(self):
        """Réinitialiser l'import"""
        self.ensure_one()
        self.state = 'draft'
        self.line_ids.unlink()
