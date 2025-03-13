from odoo import api, fields, models, _
from datetime import datetime, timedelta

class PointeurImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Ligne d\'import des données du pointeur'
    _order = 'date desc, id desc'

    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    employee_name = fields.Char(string='Nom employé', required=True)
    display_id = fields.Char(string='ID employé')
    payroll_id = fields.Char(string='ID paie')
    department = fields.Char(string='Département')
    dept_code = fields.Char(string='Code département')
    date = fields.Date(string='Date', required=True)
    check_in = fields.Datetime(string='Entrée')
    check_out = fields.Datetime(string='Sortie')
    in_note = fields.Char(string='Note d\'entrée')
    out_note = fields.Char(string='Note de sortie')
    reg_hours = fields.Float(string='Heures normales')
    ot1_hours = fields.Float(string='Heures sup. 1')
    ot2_hours = fields.Float(string='Heures sup. 2')
    total_hours = fields.Float(string='Total heures')
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    attendance_id = fields.Many2one('hr.attendance', string='Présence')
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('imported', 'Importé'),
        ('done', 'Terminé'),
        ('error', 'Erreur')
    ], string='État', default='draft', required=True)
    error_message = fields.Text(string='Message d\'erreur')

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
