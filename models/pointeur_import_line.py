from odoo import api, fields, models, _
date = datetime.strptime(row['Date'], '%m/%d/%y').date()
in_time = datetime.strptime(f"{row['Date']} {row['In Time']}", '%m/%d/%y %I:%M%p')
out_time = None
if row['Out Time'] and row['Out Day']:
    out_time = datetime.strptime(f"{date.strftime('%m/%d/%y')} {row['Out Time']}", '%m/%d/%y %I:%M%p')
    if row['Out Day'] != row['In Day']:
        out_time += timedelta(days=1)
class PointeurImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Ligne d\'import des données du pointeur'
    _order = 'date desc, id desc'
    payroll_id = fields.Char(string='ID Paie')
    dept_code = fields.Char(string='Code département')
    note = fields.Text(string='Note')
    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    display_name = fields.Char(string='Nom employé', required=True)
    display_id = fields.Char(string='ID employé')
    date = fields.Date(string='Date', required=True)
    in_day = fields.Char(string='Jour entrée')
    in_time = fields.Char(string='Heure entrée')
    out_day = fields.Char(string='Jour sortie')
    out_time = fields.Char(string='Heure sortie')
    check_in = fields.Datetime(string='Entrée', required=True)
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
    ], string='État', default='draft')
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
