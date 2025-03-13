from odoo import models, fields, api


class PointeurAttendanceType(models.Model):
    _name = 'pointeur_hr.attendance.type'
    _description = 'Type de présence'

    name = fields.Char(string='Nom', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(string='Séquence', default=10)
    color = fields.Integer(string='Couleur')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Le code doit être unique !')
    ]
