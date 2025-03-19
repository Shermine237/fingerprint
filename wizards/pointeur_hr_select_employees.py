from odoo import api, fields, models, _
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class PointeurHrSelectEmployees(models.TransientModel):
    _name = 'pointeur_hr.select.employees'
    _description = 'Assistant de sélection des employés'
    
    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True)
    line_ids = fields.One2many('pointeur_hr.select.employees.line', 'wizard_id', string='Lignes')
    mapped_count = fields.Integer(string='Lignes déjà mappées', readonly=True)
    unmapped_count = fields.Integer(string='Lignes à traiter', compute='_compute_unmapped_count')
    
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
                if line.employee_name:  # S'assurer que le nom n'est pas vide
                    lines_by_name[line.employee_name].append(line)
            
            # Créer une seule ligne de wizard par nom d'employé
            line_vals = []
            for employee_name, lines in lines_by_name.items():
                # Prendre la première ligne comme référence
                reference_line = lines[0]
                # Récupérer les IDs des lignes d'import
                import_line_ids = [l.id for l in lines]
                if not import_line_ids:  # Ne pas créer de ligne si pas de lignes d'import
                    continue
                    
                line_vals.append((0, 0, {
                    'employee_name': employee_name,
                    'line_count': len(lines),
                    'reference_line_id': reference_line.id,
                    'import_line_ids': [(6, 0, import_line_ids)],
                    'check_in': reference_line.check_in,
                    'check_out': reference_line.check_out,
                }))
            
            res['line_ids'] = line_vals
            res['mapped_count'] = len(import_record.line_ids) - len(unmapped_lines)
            
        return res
    
    def action_confirm(self):
        """Confirmer les sélections et créer les présences"""
        self.ensure_one()
        
        # Vérifier qu'au moins une ligne a un employé sélectionné
        valid_lines = self.line_ids.filtered(lambda l: l.employee_id)
        if not valid_lines:
            raise UserError(_("Veuillez sélectionner au moins un employé."))
            
        manual_mapped_count = 0
        mapped_names = []
        
        for wizard_line in valid_lines:
            # Utiliser les lignes d'import déjà associées
            import_lines = wizard_line.import_line_ids.filtered(lambda l: l.state not in ['done', 'error'])
            if not import_lines:
                continue
                
            import_lines.write({
                'employee_id': wizard_line.employee_id.id,
                'state': 'mapped'
            })
            manual_mapped_count += len(import_lines)
            if wizard_line.employee_name:  # S'assurer que le nom n'est pas vide
                mapped_names.append(wizard_line.employee_name)
            
            # Créer une correspondance permanente si demandé
            if wizard_line.create_mapping and wizard_line.employee_name and wizard_line.employee_id:
                # Vérifier si une correspondance existe déjà pour cet employé
                existing_employee_mapping = self.env['pointeur_hr.employee.mapping'].sudo().search([
                    ('employee_id', '=', wizard_line.employee_id.id),
                    '|',
                    ('active', '=', True),
                    ('active', '=', False)
                ], limit=1)
                
                if existing_employee_mapping and existing_employee_mapping.name != wizard_line.employee_name:
                    raise UserError(_("L'employé %s a déjà une correspondance avec le nom '%s'. Un employé ne peut avoir qu'une seule correspondance de nom.") 
                                   % (wizard_line.employee_id.name, existing_employee_mapping.name))
                
                # Vérifier si une correspondance existe déjà pour ce nom et cet employé
                mapping = self.env['pointeur_hr.employee.mapping'].sudo().search([
                    ('name', '=', wizard_line.employee_name),
                    ('employee_id', '=', wizard_line.employee_id.id),
                    '|',
                    ('active', '=', True),
                    ('active', '=', False)
                ], limit=1)
                
                if mapping:
                    # Réactiver et mettre à jour si nécessaire
                    mapping.sudo().write({
                        'active': True,
                        'import_count': mapping.import_count + 1,
                        'last_used': fields.Datetime.now(),
                        'import_id': self.import_id.id
                    })
                else:
                    # Créer la nouvelle correspondance
                    try:
                        self.env['pointeur_hr.employee.mapping'].sudo().create({
                            'name': wizard_line.employee_name.strip(),  # Nettoyer les espaces
                            'employee_id': wizard_line.employee_id.id,
                            'import_id': self.import_id.id,
                        })
                    except Exception as e:
                        _logger.error("Erreur lors de la création de la correspondance : %s", str(e))
                        raise UserError(_("Impossible de créer la correspondance pour %s : le nom est invalide ou vide.") % wizard_line.employee_name)
        
        # Créer les présences
        if manual_mapped_count > 0:
            self.import_id._create_attendances()
            
        # Créer le message de retour
        message = _("%d lignes ont été mappées manuellement.") % manual_mapped_count
        if mapped_names:  # Vérifier que la liste n'est pas vide
            message += _("\nEmployés mappés : %s") % ", ".join(mapped_names)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Mapping terminé"),
                'message': message,
                'type': 'success',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }

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
    create_mapping = fields.Boolean(string='Créer correspondance', default=True)
    line_count = fields.Integer(string='Nombre de lignes', readonly=True)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Mettre à jour les lignes d'import quand l'employé change"""
        if self.employee_id and not self.import_line_ids:
            # Récupérer les lignes d'import depuis la ligne de référence
            lines = self.env['pointeur_hr.import.line'].search([
                ('import_id', '=', self.wizard_id.import_id.id),
                ('employee_name', '=', self.employee_name),
                ('state', 'not in', ['done', 'error'])
            ])
            if lines:
                self.import_line_ids = [(6, 0, lines.ids)]
