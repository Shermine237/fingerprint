from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

class PointeurHrEmployeeMapping(models.Model):
    _name = 'pointeur_hr.employee.mapping'
    _description = 'Correspondance des noms importés avec les employés'
    _order = 'last_used desc, import_count desc'

    imported_name = fields.Char(string='Nom importé', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', required=True)
    last_used = fields.Datetime(string='Dernière utilisation', default=fields.Datetime.now)
    import_count = fields.Integer(string='Nombre d\'imports', default=1)
    import_ids = fields.Many2many('pointeur_hr.import', string='Imports', compute='_compute_import_ids')

    _sql_constraints = [
        ('unique_imported_name_employee', 'unique(imported_name, employee_id)', 
         'Une correspondance existe déjà pour ce nom importé et cet employé !')
    ]

    def name_get(self):
        return [(rec.id, f"{rec.imported_name} → {rec.employee_id.name}") for rec in self]

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
            ('employee_name', '=', self.imported_name),
            ('employee_id', '=', False)
        ], limit=10)
        
        # Construire le message
        message = _("<h3>Informations pour '{}'</h3>").format(self.imported_name)
        
        # Ajouter les correspondances existantes
        if other_mappings:
            message += _("<h4>Autres noms utilisés pour cet employé :</h4><ul>")
            for mapping in other_mappings:
                message += _("<li>{} (utilisé {} fois)</li>").format(
                    mapping.imported_name, mapping.import_count)
            message += "</ul>"
            
        # Ajouter les lignes d'import trouvées
        if import_lines:
            message += _("<h4>Lignes d'import avec ce nom :</h4><ul>")
            for line in import_lines:
                message += _("<li>Import #{} - {} - <a href='#' data-oe-model='pointeur_hr.import.line' data-oe-id='{}'>Voir</a></li>").format(
                    line.import_id.id, line.import_id.name, line.id)
            message += "</ul>"
        else:
            message += _("<p>Aucune ligne d'import avec ce nom n'a été trouvée.</p>")
            
        # Afficher le message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informations sur la correspondance'),
                'message': message,
                'sticky': True,
                'type': 'info',
            }
        }
    
    def action_create_mapping(self):
        """Crée une correspondance pour l'employé sélectionné"""
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Recherche des lignes d'import avec le même nom
        import_lines = self.env['pointeur_hr.import.line'].search([
            ('employee_name', '=', self.imported_name),
            ('employee_id', '=', False)
        ])
        
        # Mise à jour des lignes d'import
        for line in import_lines:
            line.write({
                'employee_id': self.employee_id.id,
                'state': 'mapped'
            })
        
        # Message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mise à jour des lignes d\'import'),
                'message': _('%d lignes d\'import mises à jour.') % len(import_lines),
                'sticky': False,
                'type': 'success',
            }
        }

    def _compute_import_ids(self):
        for record in self:
            # Rechercher les lignes d'import qui utilisent cette correspondance
            import_lines = self.env['pointeur_hr.import.line'].search([
                ('employee_name', '=', record.imported_name),
                ('employee_id', '=', record.employee_id.id)
            ])
            # Récupérer les imports associés
            record.import_ids = import_lines.mapped('import_id')
