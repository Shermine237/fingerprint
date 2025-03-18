from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

class PointeurHrEmployeeMapping(models.Model):
    _name = 'pointeur_hr.employee.mapping'
    _description = 'Correspondance des noms importés avec les employés'
    _order = 'last_used desc, import_count desc'

    name = fields.Char(string='Nom importé', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', required=True)
    last_used = fields.Datetime(string='Dernière utilisation', default=fields.Datetime.now)
    import_count = fields.Integer(string='Nombre d\'imports', default=1)
    import_id = fields.Many2one('pointeur_hr.import', string='Import d\'origine')
    import_ids = fields.Many2many('pointeur_hr.import', string='Imports', compute='_compute_import_ids')

    _sql_constraints = [
        ('unique_name_employee', 'unique(name, employee_id)', 
         'Une correspondance existe déjà pour ce nom importé et cet employé !')
    ]

    def name_get(self):
        return [(rec.id, f"{rec.name} → {rec.employee_id.name}") for rec in self]

    def action_find_similar_names(self):
        """Recherche d'autres noms qui correspondent au même employé"""
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Recherche des correspondances existantes pour cet employé
        other_mappings = self.search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id)
        ])
        
        # Recherche des lignes d'import avec le même nom
        import_lines = self.env['pointeur_hr.import.line'].search([
            ('employee_name', '=', self.name),
            ('employee_id', '=', False)
        ], limit=10)
        
        # Construire le message
        message = _("<h3>Informations pour '{}'</h3>").format(self.name)
        
        # Ajouter les correspondances existantes
        if other_mappings:
            message += _("<h4>Autres noms utilisés pour cet employé :</h4><ul>")
            for mapping in other_mappings:
                message += _("<li>{} (utilisé {} fois)</li>").format(
                    mapping.name, mapping.import_count)
            message += "</ul>"
        
        # Ajouter les lignes d'import sans correspondance
        if import_lines:
            message += _("<h4>Lignes d'import sans correspondance :</h4><ul>")
            for line in import_lines:
                message += _("<li>Import #{} - {} ({})</li>").format(
                    line.import_id.id, line.employee_name, 
                    line.check_in.strftime('%d/%m/%Y') if line.check_in else '')
            message += "</ul>"
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Analyse des correspondances'),
                'message': message,
                'sticky': True,
                'type': 'info',
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Lignes sans correspondance'),
                    'res_model': 'pointeur_hr.import.line',
                    'view_mode': 'tree,form',
                    'domain': [('employee_name', '=', self.name), ('employee_id', '=', False)],
                }
            }
        }
        
    def _compute_import_ids(self):
        """Calcule les imports qui ont utilisé cette correspondance"""
        for rec in self:
            import_lines = self.env['pointeur_hr.import.line'].search([
                ('employee_name', '=', rec.name),
                ('employee_id', '=', rec.employee_id.id)
            ])
            rec.import_ids = import_lines.mapped('import_id')
            
    def action_view_imports(self):
        """Voir les imports qui ont utilisé cette correspondance"""
        self.ensure_one()
        
        return {
            'name': _('Imports'),
            'type': 'ir.actions.act_window',
            'res_model': 'pointeur_hr.import',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.import_ids.ids)],
        }
