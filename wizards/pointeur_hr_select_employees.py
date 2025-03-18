from odoo import api, fields, models, _
from odoo.exceptions import UserError
from collections import defaultdict

class PointeurHrSelectEmployees(models.TransientModel):
    _name = 'pointeur_hr.select.employees'
    _description = 'Assistant de sélection des employés'
    
    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True)
    line_ids = fields.One2many('pointeur_hr.select.employees.line', 'wizard_id', string='Lignes')
    mapped_count = fields.Integer(string='Lignes mappées automatiquement', readonly=True)
    unmapped_count = fields.Integer(string='Lignes à mapper', compute='_compute_unmapped_count')
    
    @api.depends('line_ids')
    def _compute_unmapped_count(self):
        for wizard in self:
            wizard.unmapped_count = len(wizard.line_ids)
    
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
            
            # Regrouper les lignes par nom d'employé
            lines_by_name = defaultdict(list)
            for line in unmapped_lines:
                lines_by_name[line.employee_name].append(line)
            
            # Créer une seule ligne de wizard par nom d'employé
            line_vals = []
            for employee_name, lines in lines_by_name.items():
                # Prendre la première ligne comme référence
                reference_line = lines[0]
                line_vals.append((0, 0, {
                    'employee_name': employee_name,
                    'line_count': len(lines),
                    'reference_line_id': reference_line.id,
                    'import_line_ids': [(6, 0, [l.id for l in lines])],
                    'check_in': reference_line.check_in,
                    'check_out': reference_line.check_out,
                }))
            
            res['line_ids'] = line_vals
            res['mapped_count'] = len(import_record.line_ids) - len(unmapped_lines)
            
        return res
    
    def action_confirm(self):
        """Confirmer les sélections et créer les présences"""
        self.ensure_one()
        
        # Compter les nouvelles correspondances créées
        manual_mapped_count = 0
        
        # Mettre à jour les lignes d'import avec les employés sélectionnés
        for wizard_line in self.line_ids:
            if wizard_line.employee_id:
                # Mettre à jour toutes les lignes d'import associées
                wizard_line.import_line_ids.write({
                    'employee_id': wizard_line.employee_id.id,
                    'state': 'mapped'
                })
                manual_mapped_count += len(wizard_line.import_line_ids)
                
                # Créer une correspondance permanente si demandé
                if wizard_line.create_mapping:
                    mapping = self.env['pointeur_hr.employee.mapping'].search([
                        ('name', '=', wizard_line.employee_name),
                        ('employee_id', '=', wizard_line.employee_id.id)
                    ], limit=1)
                    
                    if not mapping:
                        self.env['pointeur_hr.employee.mapping'].create({
                            'name': wizard_line.employee_name,
                            'employee_id': wizard_line.employee_id.id,
                            'import_id': self.import_id.id,
                        })
        
        # Créer les présences
        total_mapped = self.mapped_count + manual_mapped_count
        return self.import_id._create_attendances(total_mapped)


class PointeurHrSelectEmployeesLine(models.TransientModel):
    _name = 'pointeur_hr.select.employees.line'
    _description = 'Ligne de l\'assistant de sélection des employés'
    
    wizard_id = fields.Many2one('pointeur_hr.select.employees', string='Assistant', required=True, ondelete='cascade')
    reference_line_id = fields.Many2one('pointeur_hr.import.line', string='Ligne de référence', required=True)
    import_line_ids = fields.Many2many('pointeur_hr.import.line', string='Lignes d\'import associées')
    employee_name = fields.Char(string='Nom importé', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employé')
    check_in = fields.Datetime(string='Entrée (exemple)', readonly=True)
    check_out = fields.Datetime(string='Sortie (exemple)', readonly=True)
    create_mapping = fields.Boolean(string='Créer correspondance permanente', default=True)
    line_count = fields.Integer(string='Nombre de lignes', readonly=True)
