from odoo import models, fields, api, _

class FingerprtHrLocation(models.Model):
    _name = 'fingerprt_hr.location'
    _description = 'Attendance Location'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    address = fields.Text(string='Address')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    notes = fields.Text(string='Notes')
