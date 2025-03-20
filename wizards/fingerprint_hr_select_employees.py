from odoo import api, fields, models, _
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class FingerprintHrSelectEmployees(models.TransientModel):
    _name = 'fingerprint_hr.select.employees'
    _description = 'Select Employees'
    
    import_id = fields.Many2one('fingerprint_hr.import', string='Import', required=True)
    line_ids = fields.One2many('fingerprint_hr.select.employees.line', 'wizard_id', string='Lines')
    mapped_count = fields.Integer(string='Mapped Lines', readonly=True)
    unmapped_count = fields.Integer(string='Lines to process', compute='_compute_unmapped_count')
    
    @api.depends('line_ids')
    def _compute_unmapped_count(self):
        for wizard in self:
            wizard.unmapped_count = len(wizard.line_ids)
    
    @api.model
    def default_get(self, fields_list):
        res = super(FingerprintHrSelectEmployees, self).default_get(fields_list)
        if self.env.context.get('active_model') == 'fingerprint_hr.import' and self.env.context.get('active_id'):
            import_id = self.env.context.get('active_id')
            import_record = self.env['fingerprint_hr.import'].browse(import_id)
            
            # Check that there are lines without a match
            unmapped_lines = import_record.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
            if not unmapped_lines:
                return res
                
            res['import_id'] = import_id
            
            # Group lines by employee name
            lines_by_name = defaultdict(list)
            for line in unmapped_lines:
                if line.employee_name:  # Ensure the name is not empty
                    lines_by_name[line.employee_name].append(line)
            
            # Create a single wizard line per employee name
            line_vals = []
            for employee_name, lines in lines_by_name.items():
                # Take the first line as reference
                reference_line = lines[0]
                # Get the IDs of the import lines
                import_line_ids = [l.id for l in lines]
                if not import_line_ids:  # Do not create a line if there are no import lines
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
        """Confirm selections and create attendances"""
        self.ensure_one()
        
        valid_lines = self.line_ids.filtered(lambda l: l.employee_id)
        if not valid_lines:
            raise UserError(_("Please select at least one employee."))
            
        # Check that the same employee is not assigned to multiple names
        employee_names = {}
        for line in valid_lines:
            if line.employee_id.id in employee_names:
                if employee_names[line.employee_id.id] != line.employee_name:
                    raise UserError(_(
                        "The employee '%s' is assigned to multiple different names ('%s' and '%s'). "
                        "An employee can only have one name mapping."
                    ) % (line.employee_id.name, employee_names[line.employee_id.id], line.employee_name))
            else:
                employee_names[line.employee_id.id] = line.employee_name
            
        manual_mapped_count = 0
        mapped_names = []
        
        for wizard_line in valid_lines:
            # Use the already associated import lines
            import_lines = wizard_line.import_line_ids.filtered(lambda l: l.state not in ['done', 'error'])
            if not import_lines:
                continue
                
            import_lines.write({
                'employee_id': wizard_line.employee_id.id,
                'state': 'mapped'
            })
            manual_mapped_count += len(import_lines)
            if wizard_line.employee_name:  # Ensure the name is not empty
                mapped_names.append(wizard_line.employee_name)
            
            # Create a permanent mapping if requested
            if wizard_line.create_mapping and wizard_line.employee_name and wizard_line.employee_id:
                # Check if a mapping already exists for this employee
                existing_employee_mapping = self.env['fingerprint_hr.employee.mapping'].sudo().search([
                    ('employee_id', '=', wizard_line.employee_id.id),
                    '|',
                    ('active', '=', True),
                    ('active', '=', False)
                ], limit=1)
                
                if existing_employee_mapping and existing_employee_mapping.name != wizard_line.employee_name:
                    raise UserError(_("The employee %s has already a mapping with the name '%s'. An employee can only have one name mapping.") 
                                   % (wizard_line.employee_id.name, existing_employee_mapping.name))
                
                # Check if a mapping already exists for this name and employee
                mapping = self.env['fingerprint_hr.employee.mapping'].sudo().search([
                    ('name', '=', wizard_line.employee_name),
                    ('employee_id', '=', wizard_line.employee_id.id),
                    '|',
                    ('active', '=', True),
                    ('active', '=', False)
                ], limit=1)
                
                if mapping:
                    # Reactivate and update if necessary
                    mapping.sudo().write({
                        'active': True,
                        'import_count': mapping.import_count + 1,
                        'last_used': fields.Datetime.now(),
                        'import_id': self.import_id.id
                    })
                else:
                    # Create the new mapping
                    try:
                        self.env['fingerprint_hr.employee.mapping'].sudo().create({
                            'name': wizard_line.employee_name.strip(),  # Clean spaces
                            'employee_id': wizard_line.employee_id.id,
                            'import_id': self.import_id.id,
                        })
                    except Exception as e:
                        raise UserError(_("Unable to create mapping for %s : the name is invalid or empty.") % wizard_line.employee_name)
        
        # Create attendances
        if manual_mapped_count > 0:
            self.import_id._create_attendances()
            
        # Create return message
        message = _("%d lines have been manually mapped.") % manual_mapped_count
        if mapped_names:  # Check that the list is not empty
            message += _("\nMapped employees : %s") % ", ".join(mapped_names)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Mapping completed"),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }

class FingerprintHrSelectEmployeesLine(models.TransientModel):
    _name = 'fingerprint_hr.select.employees.line'
    _description = 'Line of the selection assistant'
    
    wizard_id = fields.Many2one('fingerprint_hr.select.employees', string='Assistant', required=True, ondelete='cascade')
    reference_line_id = fields.Many2one('fingerprint_hr.import.line', string='Reference line', required=True)
    import_line_ids = fields.Many2many('fingerprint_hr.import.line', string='Import lines associated')
    employee_name = fields.Char(string='Imported name', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee')
    check_in = fields.Datetime(string='Check-in (example)', readonly=True)
    check_out = fields.Datetime(string='Check-out (example)', readonly=True)
    create_mapping = fields.Boolean(string='Create mapping', default=True)
    line_count = fields.Integer(string='Number of lines', readonly=True)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Update import lines when employee changes"""
        # Check if the employee is already assigned to another name in the wizard
        if self.employee_id:
            other_lines = self.wizard_id.line_ids.filtered(
                lambda l: l.id != self.id and l.employee_id.id == self.employee_id.id and l.employee_name != self.employee_name
            )
            if other_lines:
                # Get the employee name before resetting
                employee_name = self.employee_id.name
                # Reset the employee and show a warning
                self.employee_id = False
                return {
                    'warning': {
                        'title': _("Employee already assigned"),
                        'message': _(
                            "The employee '%s' is already assigned to the name '%s'. "
                            "An employee can only have one name mapping."
                        ) % (employee_name, other_lines[0].employee_name)
                    }
                }
            
            # Check if the employee already has a mapping in the database
            if self.employee_id and self.employee_name:
                existing_mapping = self.env['fingerprint_hr.employee.mapping'].search([
                    ('employee_id', '=', self.employee_id.id),
                    ('name', '!=', self.employee_name),
                    '|',
                    ('active', '=', True),
                    ('active', '=', False)
                ], limit=1)
                
                if existing_mapping:
                    # Show a warning but do not reset the employee
                    return {
                        'warning': {
                            'title': _("Existing mapping"),
                            'message': _(
                                "The employee '%s' has already a mapping with the name '%s'. "
                                "If you continue, you will not be able to create a mapping for this employee."
                            ) % (self.employee_id.name, existing_mapping.name)
                        }
                    }
        
        # Update import lines
        if self.employee_id and not self.import_line_ids:
            # Get import lines from the reference line
            lines = self.env['fingerprint_hr.import.line'].search([
                ('import_id', '=', self.wizard_id.import_id.id),
                ('employee_name', '=', self.employee_name),
                ('state', 'not in', ['done', 'error'])
            ])
            if lines:
                self.import_line_ids = [(6, 0, lines.ids)]
