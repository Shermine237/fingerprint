from odoo import models, fields, api, _

class PointeurLocation(models.Model):
    _name = 'pointeur_hr.location'
    _description = 'Lieu de pointage'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    code = fields.Char(string='Code', required=True)
    active = fields.Boolean(string='Actif', default=True)
    note = fields.Text(string='Note')
    
    # Relations
    employee_ids = fields.One2many('hr.employee', 'default_location_id', string='Employés')
    
    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Le code doit être unique !')
    ]
