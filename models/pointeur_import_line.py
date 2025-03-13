from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError

class PointeurImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Ligne d\'import des données du pointeur'
    _order = 'date, employee_name'

    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    employee_name = fields.Char(string='Nom employé', required=True)
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
        # Si on met à jour l'attendance_id, on met à jour l'état
        if 'attendance_id' in vals and vals['attendance_id']:
            vals['state'] = 'done'
        return super(PointeurImportLine, self).write(vals)

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
