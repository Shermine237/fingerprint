from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PointeurHrSelectEmployees(models.TransientModel):
    _name = 'pointeur_hr.select.employees'
    _description = 'Assistant de sélection des employés'
    
    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True)
    line_ids = fields.One2many('pointeur_hr.select.employees.line', 'wizard_id', string='Lignes')
    
    @api.model
    def default_get(self, fields_list):
        res = super(PointeurHrSelectEmployees, self).default_get(fields_list)
        if self.env.context.get('active_model') == 'pointeur_hr.import' and self.env.context.get('active_id'):
            import_id = self.env.context.get('active_id')
            import_record = self.env['pointeur_hr.import'].browse(import_id)
            
            # Vérifier qu'il y a des lignes sans correspondance
            unmapped_lines = import_record.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
            if not unmapped_lines:
                return res
                
            res['import_id'] = import_id
            
            # Créer les lignes du wizard
            line_vals = []
            for line in unmapped_lines:
                line_vals.append((0, 0, {
                    'import_line_id': line.id,
                    'employee_name': line.employee_name,
                    'check_in': line.check_in,
                    'check_out': line.check_out,
                }))
                
            res['line_ids'] = line_vals
            
        return res
    
    def action_confirm(self):
        """Confirmer les sélections et créer les présences"""
        self.ensure_one()
        
        # Mettre à jour les lignes d'import avec les employés sélectionnés
        for line in self.line_ids:
            if line.employee_id:
                line.import_line_id.write({
                    'employee_id': line.employee_id.id,
                    'state': 'mapped'
                })
                
                # Créer une correspondance permanente si demandé
                if line.create_mapping:
                    mapping = self.env['pointeur_hr.employee.mapping'].search([
                        ('imported_name', '=', line.employee_name),
                        ('employee_id', '=', line.employee_id.id)
                    ], limit=1)
                    
                    if not mapping:
                        self.env['pointeur_hr.employee.mapping'].create({
                            'imported_name': line.employee_name,
                            'employee_id': line.employee_id.id
                        })
        
        # Créer les présences
        self.import_id.action_create_attendances()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Présences créées'),
                'message': _('Les présences ont été créées avec succès.'),
                'sticky': False,
                'type': 'success',
            }
        }
        
class PointeurHrSelectEmployeesLine(models.TransientModel):
    _name = 'pointeur_hr.select.employees.line'
    _description = 'Ligne de l\'assistant de sélection des employés'
    
    wizard_id = fields.Many2one('pointeur_hr.select.employees', string='Assistant', required=True, ondelete='cascade')
    import_line_id = fields.Many2one('pointeur_hr.import.line', string='Ligne d\'import', required=True)
    employee_name = fields.Char(string='Nom importé', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employé')
    check_in = fields.Datetime(string='Entrée', readonly=True)
    check_out = fields.Datetime(string='Sortie', readonly=True)
    create_mapping = fields.Boolean(string='Créer correspondance permanente', default=True)
