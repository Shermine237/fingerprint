from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError

class PointeurHrImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Ligne d\'import des données du pointeur'
    _order = 'date, employee_name'

    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    employee_name = fields.Char(string='Nom employé', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employé correspondant')
    display_id = fields.Char(string='ID Badge')
    payroll_id = fields.Char(string='ID Paie')
    department = fields.Char(string='Département')
    dept_code = fields.Char(string='Code département')
    date = fields.Date(string='Date', required=True)
    check_in = fields.Datetime(string='Entrée')  # Non requis car peut être vide
    check_out = fields.Datetime(string='Sortie')
    in_note = fields.Char(string='Note entrée')
    out_note = fields.Char(string='Note sortie')
    reg_hours = fields.Float(string='Heures normales')
    ot1_hours = fields.Float(string='Heures sup. 1')
    ot2_hours = fields.Float(string='Heures sup. 2')
    total_hours = fields.Float(string='Total heures', compute='_compute_hours')
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    attendance_id = fields.Many2one('hr.attendance', string='Présence')
    error_message = fields.Text(string='Message d\'erreur')
    notes = fields.Text(string='Notes')

    state = fields.Selection([
        ('imported', 'Importé'),
        ('mapped', 'Correspondance trouvée'),
        ('done', 'Terminé'),
        ('error', 'Erreur')
    ], string='État', default='imported', required=True)

    @api.depends('check_in', 'check_out')
    def _compute_hours(self):
        for line in self:
            if line.check_in and line.check_out:
                delta = line.check_out - line.check_in
                line.total_hours = delta.total_seconds() / 3600.0
            else:
                line.total_hours = 0.0

    def write(self, vals):
        # Si on met à jour l'employee_id, on met à jour l'état et on crée/met à jour la correspondance
        if 'employee_id' in vals and vals['employee_id']:
            vals['state'] = 'mapped'
            for record in self:
                if record.employee_name:  # On vérifie qu'il y a un nom à mapper
                    mapping = self.env['pointeur_hr.employee.mapping'].search(
                        [('imported_name', '=', record.employee_name)], limit=1)
                    if mapping:
                        mapping.write({
                            'employee_id': vals['employee_id'],
                            'last_used': fields.Datetime.now(),
                            'import_count': mapping.import_count + 1
                        })
                    else:
                        self.env['pointeur_hr.employee.mapping'].create({
                            'imported_name': record.employee_name,
                            'employee_id': vals['employee_id'],
                        })

        # Si on met à jour l'attendance_id, on met à jour l'état
        if 'attendance_id' in vals and vals['attendance_id']:
            vals['state'] = 'done'
        return super(PointeurHrImportLine, self).write(vals)

    def action_view_attendance(self):
        """Voir la présence associée"""
        self.ensure_one()
        if self.attendance_id:
            return {
                'name': _('Présence'),
                'type': 'ir.actions.act_window',
                'res_model': 'hr.attendance',
                'view_mode': 'form',
                'res_id': self.attendance_id.id,
            }
        return True

    @api.constrains('check_in', 'check_out')
    def _check_validity(self):
        """ Vérifie la validité des heures d'entrée et de sortie """
        for record in self:
            if record.check_in and record.check_out and record.check_out < record.check_in:
                raise ValidationError(_('La date/heure de sortie ne peut pas être antérieure à la date/heure d\'entrée.'))

    def find_employee_mapping(self):
        """Recherche automatique des correspondances employés"""
        for record in self:
            if not record.employee_id and record.employee_name:
                # Chercher d'abord dans les correspondances existantes
                mapping = self.env['pointeur_hr.employee.mapping'].search(
                    [('imported_name', '=', record.employee_name)], limit=1)
                if mapping:
                    record.write({'employee_id': mapping.employee_id.id})
                    continue

                # Si pas de correspondance, utiliser la recherche intelligente
                employee = self.env['pointeur_hr.import']._find_employee_by_name(record.employee_name)
                if employee:
                    record.write({'employee_id': employee.id})
        
        # Message de notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recherche de correspondance'),
                'message': _('Recherche terminée.'),
                'sticky': False,
                'type': 'info',
            }
        }
    
    def action_create_mapping(self):
        """Créer une correspondance pour cette ligne"""
        self.ensure_one()
        
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Vérifier si une correspondance existe déjà
        existing = self.env['pointeur_hr.employee.mapping'].search([
            ('name', '=', self.employee_name)
        ], limit=1)
        
        if existing:
            # Mettre à jour la correspondance existante
            existing.write({
                'employee_id': self.employee_id.id,
                'last_used': fields.Datetime.now(),
                'import_count': existing.import_count + 1
            })
            message = _("Correspondance mise à jour : %s -> %s") % (self.employee_name, self.employee_id.name)
        else:
            # Créer une nouvelle correspondance
            self.env['pointeur_hr.employee.mapping'].create({
                'name': self.employee_name,
                'employee_id': self.employee_id.id,
                'import_id': self.import_id.id,
            })
            message = _("Nouvelle correspondance créée : %s -> %s") % (self.employee_name, self.employee_id.name)
            
        # Mettre à jour l'état de la ligne
        self.write({'state': 'mapped'})
        
        # Afficher un message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correspondance créée'),
                'message': message,
                'sticky': False,
                'type': 'success',
            }
        }
