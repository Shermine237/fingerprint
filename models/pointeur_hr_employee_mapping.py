from odoo import api, fields, models

class PointeurHrEmployeeMapping(models.Model):
    _name = 'pointeur_hr.employee.mapping'
    _description = 'Correspondance des noms importés avec les employés'
    _rec_name = 'imported_name'

    imported_name = fields.Char(string='Nom importé', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', required=True)
    last_used = fields.Datetime(string='Dernière utilisation', default=fields.Datetime.now)
    import_count = fields.Integer(string='Nombre d\'imports', default=1)

    _sql_constraints = [
        ('unique_imported_name', 'unique(imported_name)', 
         'Une correspondance existe déjà pour ce nom importé !')
    ]

    def name_get(self):
        return [(rec.id, f"{rec.imported_name} → {rec.employee_id.name}") for rec in self]
