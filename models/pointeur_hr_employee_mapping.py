from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class PointeurHrEmployeeMapping(models.Model):
    _name = 'pointeur_hr.employee.mapping'
    _description = 'Mapping between imported names and employees'
    _order = 'last_used desc, import_count desc'

    name = fields.Char(string='Imported Name', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    last_used = fields.Datetime(string='Last Used', default=fields.Datetime.now)
    import_count = fields.Integer(string='Import Count', default=1)
    import_id = fields.Many2one('pointeur_hr.import', string='Source Import')
    import_ids = fields.Many2many('pointeur_hr.import', string='Imports', compute='_compute_import_ids')
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('unique_name_active', 'unique(name, active)',
         'A mapping already exists for this imported name!'),
        ('unique_employee_active', 'unique(employee_id, active)',
         'This employee already has an active name mapping!')
    ]

    @api.constrains('name', 'employee_id', 'active')
    def _check_unique_constraints(self):
        """Additional check to prevent duplicates"""
        for record in self:
            if not record.active:
                continue  # Ignore inactive records
                
            # Check if another active record exists with the same name
            same_name = self.search([
                ('id', '!=', record.id),
                ('name', '=', record.name),
                ('active', '=', True)
            ], limit=1)
            
            if same_name:
                raise ValidationError(_(
                    "An active mapping already exists for name '%s' (associated with employee %s)."
                ) % (record.name, same_name.employee_id.name))
            
            # Check if another active record exists for the same employee
            same_employee = self.search([
                ('id', '!=', record.id),
                ('employee_id', '=', record.employee_id.id),
                ('active', '=', True)
            ], limit=1)
            
            if same_employee:
                raise ValidationError(_(
                    "Employee %s already has an active mapping with name '%s'."
                ) % (record.employee_id.name, same_employee.name))

    @api.model_create_multi
    def create(self, vals_list):
        """Override creation to check for duplicates and log"""
        result = self.env['pointeur_hr.employee.mapping']
        
        for vals in vals_list:
            _logger.info("Creating mapping: %s -> %s", 
                        vals.get('name'), vals.get('employee_id'))
            
            # Check if a mapping with the same name already exists
            existing_name = self.search([
                ('name', '=', vals.get('name')),
                ('active', '=', True)
            ], limit=1)
            
            if existing_name:
                _logger.warning("An active mapping already exists for name '%s'", vals.get('name'))
                continue
                
            # Check if the employee already has an active mapping
            existing_employee = self.search([
                ('employee_id', '=', vals.get('employee_id')),
                ('active', '=', True)
            ], limit=1)
            
            if existing_employee:
                _logger.warning("Employee already has an active mapping with name '%s'", existing_employee.name)
                continue
                
            # Check if an inactive mapping exists for this combination
            inactive = self.search([
                ('name', '=', vals.get('name')),
                ('employee_id', '=', vals.get('employee_id')),
                ('active', '=', False)
            ], limit=1)
            
            if inactive:
                _logger.info("Reactivating existing mapping")
                inactive.write({
                    'active': True,
                    'import_count': inactive.import_count + 1,
                    'last_used': fields.Datetime.now()
                })
                result |= inactive
            else:
                # Create a new mapping
                record = super(PointeurHrEmployeeMapping, self).create([vals])[0]
                result |= record
                
        return result

    def name_get(self):
        return [(rec.id, f"{rec.name} → {rec.employee_id.name}") for rec in self]

    def action_find_similar_names(self):
        """Find other names that map to the same employee"""
        self.ensure_one()
        _logger.info("Finding similar names for %s", self.name)
        
        if not self.employee_id:
            raise UserError(_("You must first select an employee."))
            
        # Find existing mappings for this employee
        other_mappings = self.search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('active', '=', True)
        ])
        _logger.info("Found %d other mappings", len(other_mappings))
        
        # Find import lines with the same name
        import_lines = self.env['pointeur_hr.import.line'].search([
            ('employee_name', '=', self.name),
            ('employee_id', '=', False),
            ('state', '!=', 'done')
        ], limit=10)
        _logger.info("Found %d import lines without mapping", len(import_lines))
        
        # Build the message
        message_parts = []
        message_parts.append(_("<h3>Information for '{}'</h3>").format(self.name))
        
        # Add existing mappings
        if other_mappings:
            message_parts.append(_("<h4>Other names used for this employee :</h4><ul>"))
            for mapping in other_mappings:
                message_parts.append(_("<li>{} (used {} times)</li>").format(
                    mapping.name, mapping.import_count))
            message_parts.append("</ul>")
        
        # Add import lines without mapping
        if import_lines:
            message_parts.append(_("<h4>Import lines without mapping :</h4><ul>"))
            for line in import_lines:
                message_parts.append(_("<li>Import #{} - {} ({})</li>").format(
                    line.import_id.id, line.employee_name, 
                    line.check_in.strftime('%d/%m/%Y') if line.check_in else ''))
            message_parts.append("</ul>")
            
        message = ''.join(message_parts)
        _logger.info("Generated message: %s", message)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mapping Analysis'),
                'message': message,
                'sticky': True,
                'type': 'info',
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Import Lines without Mapping'),
                    'res_model': 'pointeur_hr.import.line',
                    'view_mode': 'tree,form',
                    'domain': [
                        ('employee_name', '=', self.name),
                        ('employee_id', '=', False),
                        ('state', '!=', 'done')
                    ],
                }
            }
        }
        
    def _compute_import_ids(self):
        """Compute all imports where this mapping was used"""
        for rec in self:
            import_lines = self.env['pointeur_hr.import.line'].search([
                ('employee_name', '=', rec.name),
                ('employee_id', '=', rec.employee_id.id)
            ])
            rec.import_ids = import_lines.mapped('import_id')
            
    def action_view_imports(self):
        """View imports where this mapping was used"""
        self.ensure_one()
        _logger.info("Viewing imports for mapping %s", self.name)
        
        return {
            'name': _('Related Imports'),
            'type': 'ir.actions.act_window',
            'res_model': 'pointeur_hr.import',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.import_ids.ids)],
        }
        
    def action_deactivate(self):
        """Deactivate a mapping"""
        self.ensure_one()
        _logger.info("Deactivating mapping %s", self.name)
        
        self.write({'active': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mapping Deactivated'),
                'message': _("Mapping '{}' has been deactivated").format(self.name),
                'sticky': False,
                'type': 'success'
            }
        }
