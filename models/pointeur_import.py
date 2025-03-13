from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
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
    file_name = fields.Char(string='Nom du fichier')
    import_date = fields.Datetime(string='Date d\'import', readonly=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    line_count = fields.Integer(string='Nombre de lignes', compute='_compute_line_count')
    attendance_count = fields.Integer(string='Nombre de présences', compute='_compute_attendance_count')
    
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('imported', 'Données importées'),
        ('done', 'Présences créées'),
        ('cancelled', 'Annulé'),
        ('error', 'Erreur')
    ], string='État', default='draft', required=True, tracking=True)

    line_ids = fields.One2many('pointeur_hr.import.line', 'import_id', string='Lignes importées')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends('line_ids.attendance_id')
    def _compute_attendance_count(self):
        for record in self:
            record.attendance_count = len(record.line_ids.filtered(lambda l: l.attendance_id))

    @api.constrains('file_name')
    def _check_file_extension(self):
        """Vérifier que le fichier est un CSV"""
        for record in self:
            if record.file_name and not record.file_name.lower().endswith('.csv'):
                raise ValidationError(_("Seuls les fichiers CSV sont acceptés."))

    def action_import(self):
        """Importer les données du fichier CSV"""
        self.ensure_one()

        if not self.file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))

        # Lecture du fichier CSV
        csv_data = base64.b64decode(self.file)
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)
        success_count = 0
        error_lines = []

        # Suppression des anciennes lignes
        self.line_ids.unlink()

        # Affichage des en-têtes pour le débogage
        headers = reader.fieldnames
        self.message_post(body=_("En-têtes du fichier CSV:\n%s") % ', '.join(headers))

        for row in reader:
            try:
                # Validation des données requises
                if not row.get('Display Name', '').strip():
                    continue  # Ignorer les lignes vides

                # Affichage de la première ligne pour le débogage
                if reader.line_num == 2:  # La première ligne est l'en-tête
                    self.message_post(body=_("Exemple de ligne:\n%s") % str(row))

                # Nettoyage et conversion des dates
                in_time = row.get('In Time', '').strip()
                out_time = row.get('Out Time', '').strip()
                in_day = row.get('In Day', '').strip()
                out_day = row.get('Out Day', '').strip()

                # Au moins une heure doit être présente
                if not in_time and not out_time:
                    continue  # Ignorer les lignes sans heures
                
                # Conversion du format de date
                check_in = None
                if in_time and in_day:
                    try:
                        # Convertir 'a' en 'AM' et 'p' en 'PM'
                        in_time = in_time.replace('a', ' AM').replace('p', ' PM')
                        check_in = datetime.strptime(f"{row['Date']} {in_time}", '%m/%d/%y %I:%M %p')
                    except ValueError as e:
                        raise ValueError(f"Erreur de format pour l'heure d'entrée. Format attendu: 'MM/DD/YY HH:MMa/p', reçu: '{row['Date']} {in_time}'. Erreur: {str(e)}")

                check_out = None
                if out_time:
                    try:
                        out_time = out_time.replace('a', ' AM').replace('p', ' PM')
                        check_out = datetime.strptime(f"{row['Date']} {out_time}", '%m/%d/%y %I:%M %p')
                        # Si la sortie est le lendemain
                        if out_day and in_day and out_day != in_day:
                            check_out += timedelta(days=1)
                    except ValueError as e:
                        raise ValueError(f"Erreur de format pour l'heure de sortie. Format attendu: 'MM/DD/YY HH:MMa/p', reçu: '{row['Date']} {out_time}'. Erreur: {str(e)}")

                # Validation de la cohérence des heures
                if check_in and check_out and check_out < check_in:
                    raise ValueError("L'heure de sortie ne peut pas être antérieure à l'heure d'entrée")

                # Création de la ligne d'import
                vals = {
                    'import_id': self.id,
                    'display_id': row.get('Display ID', '').strip(),
                    'display_name': row.get('Display Name', '').strip(),
                    'department': row.get('Department', '').strip(),
                    'dept_code': row.get('Dept. Code', '').strip(),
                    'payroll_id': row.get('Payroll ID', '').strip(),
                    'date': datetime.strptime(row['Date'], '%m/%d/%y').date(),
                    'in_day': in_day,
                    'in_time': in_time,
                    'out_day': out_day,
                    'out_time': out_time,
                    'check_in': check_in,
                    'check_out': check_out,
                    'in_note': row.get('In Note', '').strip(),
                    'out_note': row.get('Out Note', '').strip(),
                    'reg_hours': float(row.get('REG', 0)),
                    'ot1_hours': float(row.get('OT1', 0)),
                    'ot2_hours': float(row.get('OT2', 0)),
                    'total_hours': float(row.get('Total', 0))
                }

                # Création de la ligne
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
                    domain = []
                    if line.display_id:
                        domain = [('barcode', '=', line.display_id)]
                    else:
                        domain = [('name', '=', line.display_name)]
                    
                    employee = self.env['hr.employee'].search(domain, limit=1)
                    if not employee:
                        line.state = 'error'
                        line.error_message = f"Employé non trouvé : {line.display_name} (ID: {line.display_id or 'Non défini'})"
                        continue

                    # Création de la présence
                    attendance_vals = {
                        'employee_id': employee.id,
                        'check_in': line.check_in,
                        'check_out': line.check_out,
                        'source': 'import',
                        'note': f"IN: {line.in_note or ''}\nOUT: {line.out_note or ''}"
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
