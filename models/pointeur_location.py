from odoo import models, fields, api, _

class PointeurLocation(models.Model):
    _name = 'pointeur_hr.location'
    _description = 'Lieu de pointage'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    address = fields.Text(string='Adresse')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    notes = fields.Text(string='Notes')
