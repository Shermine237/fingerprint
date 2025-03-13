from odoo import api, fields, models, _
from datetime import datetime, timedelta

class PointeurImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Ligne d\'import des données du pointeur'
    _order = 'date desc, id desc'

    payroll_id = fields.Char(string='ID Paie')
    dept_code = fields.Char(string='Code département')
    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    display_name = fields.Char(string='Nom employé', required=True)
    display_id = fields.Char(string='ID employé')
    date = fields.Date(string='Date')
    in_day = fields.Char(string='Jour entrée')
    in_time = fields.Char(string='Heure entrée')
    out_day = fields.Char(string='Jour sortie')
    out_time = fields.Char(string='Heure sortie')
    check_in = fields.Datetime(string='Entrée')
    check_out = fields.Datetime(string='Sortie')
    department = fields.Char(string='Département')
    reg_hours = fields.Float(string='Heures normales')
    ot1_hours = fields.Float(string='Heures sup. 1')
    ot2_hours = fields.Float(string='Heures sup. 2')
    total_hours = fields.Float(string='Total heures')
    attendance_id = fields.Many2one('hr.attendance', string='Présence')
    state = fields.Selection([
        ('draft', 'En attente'),
        ('done', 'Terminé'),
        ('error', 'Erreur')
    ], string='État', default='draft', required=True, tracking=True)
    error_message = fields.Text(string='Message d\'erreur')
    in_note = fields.Text(string='Note entrée')
    out_note = fields.Text(string='Note sortie')

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
